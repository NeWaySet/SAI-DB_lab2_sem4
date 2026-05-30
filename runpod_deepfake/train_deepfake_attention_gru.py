import argparse
import json
import random
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from tqdm import tqdm


DATASET_SLUG = "ciplab/real-and-fake-face-detection"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class RunConfig:
    profile: str
    dataset_slug: str
    image_size: int
    epochs: int
    min_epochs: int
    target_minutes: float | None
    batch_size: int
    max_per_class: int | None
    learning_rate: float
    weight_decay: float
    seed: int
    amp: bool


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True


def resolve_dataset(data_dir: str | None) -> Path:
    if data_dir:
        root = Path(data_dir).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Dataset directory does not exist: {root}")
        return root
    return download_dataset_with_kaggle_cli(DATASET_SLUG)


def download_dataset_with_kaggle_cli(dataset_slug: str) -> Path:
    kaggle_bin = shutil.which("kaggle")
    if kaggle_bin is None:
        raise RuntimeError(
            "kaggle CLI is not installed. Run `pip install kaggle`, or download the dataset "
            "manually and pass --data_dir."
        )

    safe_name = dataset_slug.replace("/", "__")
    target_dir = Path("data") / safe_name
    target_dir.mkdir(parents=True, exist_ok=True)

    has_images = any(path.suffix.lower() in IMAGE_EXTENSIONS for path in target_dir.rglob("*"))
    if not has_images:
        command = [
            kaggle_bin,
            "datasets",
            "download",
            "-d",
            dataset_slug,
            "-p",
            str(target_dir),
            "--unzip",
        ]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Could not download the Kaggle dataset. Add kaggle.json to "
                "~/.kaggle/kaggle.json or set KAGGLE_USERNAME and KAGGLE_KEY."
            ) from exc

    return target_dir.resolve()


def apply_profile(args):
    profiles = {
        "rtx-pro-6000-1h": {
            "image_size": 384,
            "epochs": 80,
            "min_epochs": 14,
            "target_minutes": 55.0,
            "batch_size": 96,
            "max_per_class": 5000,
            "learning_rate": 3e-4,
            "weight_decay": 1e-4,
            "num_workers": 12,
            "amp": True,
        },
        "rtx-5090-1h": {
            "image_size": 320,
            "epochs": 60,
            "min_epochs": 12,
            "target_minutes": 50.0,
            "batch_size": 128,
            "max_per_class": 3000,
            "learning_rate": 3e-4,
            "weight_decay": 1e-4,
            "num_workers": 8,
            "amp": True,
        },
    }
    if args.profile == "custom":
        defaults = {
            "image_size": 224,
            "epochs": 10,
            "min_epochs": 1,
            "target_minutes": None,
            "batch_size": 128,
            "max_per_class": 1500,
            "learning_rate": 3e-4,
            "weight_decay": 1e-4,
            "num_workers": 8,
            "amp": False,
        }
    else:
        defaults = profiles[args.profile]

    for key, value in defaults.items():
        if getattr(args, key) is None:
            setattr(args, key, value)
    if args.min_epochs > args.epochs:
        args.min_epochs = args.epochs
    return args


def infer_label(path: Path, root: Path) -> int | None:
    parts = [part.lower() for part in path.relative_to(root).parts[:-1]]
    if any(part in {"training_fake", "fake", "fakes"} or part.startswith("fake") for part in parts):
        return 1
    if any(part in {"training_real", "real", "reals"} or part.startswith("real") for part in parts):
        return 0
    return None


def collect_images(root: Path, max_per_class: int | None, seed: int) -> pd.DataFrame:
    rows = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label = infer_label(path, root)
        if label is None:
            continue
        rows.append({"path": str(path), "label": label})

    if not rows:
        raise RuntimeError(f"No real/fake images found under {root}")

    df = pd.DataFrame(rows).drop_duplicates("path")
    rng = np.random.default_rng(seed)
    if max_per_class:
        limited = []
        for label in [0, 1]:
            part = df[df["label"] == label].sample(frac=1.0, random_state=seed)
            limited.append(part.head(max_per_class))
        df = pd.concat(limited, ignore_index=True)
        df = df.iloc[rng.permutation(len(df))].reset_index(drop=True)
    return df


def split_dataframe(df: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df, temp_df = train_test_split(df, test_size=0.30, stratify=df["label"], random_state=seed)
    val_df, test_df = train_test_split(temp_df, test_size=0.50, stratify=temp_df["label"], random_state=seed)
    return train_df.reset_index(drop=True), val_df.reset_index(drop=True), test_df.reset_index(drop=True)


class FaceDataset(Dataset):
    def __init__(self, frame: pd.DataFrame, transform):
        self.frame = frame.reset_index(drop=True)
        self.transform = transform

    def __len__(self):
        return len(self.frame)

    def __getitem__(self, idx):
        row = self.frame.iloc[idx]
        image = Image.open(row.path).convert("RGB")
        tensor = self.transform(image)
        label = torch.tensor(float(row.label), dtype=torch.float32)
        return tensor, label, row.path


class CNNBiGRUAttention(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            self.block(3, 32, stride=2),
            self.block(32, 64, stride=2),
            self.block(64, 128, stride=2),
            self.block(128, 256, stride=2),
        )
        self.gru = nn.GRU(256, 128, num_layers=1, batch_first=True, bidirectional=True)
        self.attention = nn.Sequential(
            nn.Linear(256, 128),
            nn.Tanh(),
            nn.Linear(128, 1),
        )
        self.classifier = nn.Sequential(
            nn.LayerNorm(256),
            nn.Dropout(0.30),
            nn.Linear(256, 1),
        )

    @staticmethod
    def block(in_channels, out_channels, stride):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.SiLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.SiLU(inplace=True),
        )

    def forward(self, x, return_attention=False):
        feature_map = self.features(x)
        tokens = feature_map.flatten(2).transpose(1, 2)
        sequence, _ = self.gru(tokens)
        scores = self.attention(sequence).squeeze(-1)
        weights = torch.softmax(scores, dim=1)
        context = torch.sum(sequence * weights.unsqueeze(-1), dim=1)
        logits = self.classifier(context).squeeze(-1)
        if return_attention:
            h, w = feature_map.shape[-2:]
            return logits, weights.reshape(x.shape[0], h, w)
        return logits


def build_transforms(image_size: int):
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    train_tf = transforms.Compose(
        [
            transforms.Resize((image_size + 24, image_size + 24)),
            transforms.RandomResizedCrop(image_size, scale=(0.75, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.18, contrast=0.18, saturation=0.12),
            transforms.ToTensor(),
            normalize,
        ]
    )
    eval_tf = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            normalize,
        ]
    )
    return train_tf, eval_tf


def run_epoch(model, loader, criterion, optimizer, scaler, device, train: bool, amp: bool):
    model.train(train)
    losses, labels, probs = [], [], []
    iterator = tqdm(loader, leave=False, desc="train" if train else "eval")
    for images, targets, _ in iterator:
        images = images.to(device, non_blocking=True)
        targets = targets.to(device, non_blocking=True)
        with torch.set_grad_enabled(train):
            with torch.autocast(device_type="cuda", enabled=amp and device.type == "cuda"):
                logits = model(images)
                loss = criterion(logits, targets)
            if train:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
        probability = torch.sigmoid(logits.detach()).cpu().numpy()
        losses.append(loss.detach().item())
        labels.extend(targets.detach().cpu().numpy().astype(int).tolist())
        probs.extend(probability.tolist())
        iterator.set_postfix(loss=f"{np.mean(losses):.4f}")
    return summarize(labels, probs, np.mean(losses))


def summarize(labels, probs, loss=None):
    y_true = np.array(labels).astype(int)
    y_prob = np.array(probs)
    y_pred = (y_prob >= 0.5).astype(int)
    metrics = {
        "loss": None if loss is None else float(loss),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else None,
    }
    return metrics, y_true, y_prob, y_pred


@torch.no_grad()
def evaluate_with_paths(model, loader, device, amp: bool):
    model.eval()
    labels, probs, paths = [], [], []
    for images, targets, batch_paths in tqdm(loader, leave=False, desc="test"):
        images = images.to(device, non_blocking=True)
        with torch.autocast(device_type="cuda", enabled=amp and device.type == "cuda"):
            logits = model(images)
        labels.extend(targets.numpy().astype(int).tolist())
        probs.extend(torch.sigmoid(logits).cpu().numpy().tolist())
        paths.extend(batch_paths)
    metrics, y_true, y_prob, y_pred = summarize(labels, probs)
    return metrics, y_true, y_prob, y_pred, paths


def plot_history(history: list[dict], out_dir: Path) -> None:
    epochs = [row["epoch"] for row in history]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(epochs, [row["train_loss"] for row in history], label="train")
    axes[0].plot(epochs, [row["val_loss"] for row in history], label="val")
    axes[0].set_title("Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].legend()
    axes[1].plot(epochs, [row["train_f1"] for row in history], label="train")
    axes[1].plot(epochs, [row["val_f1"] for row in history], label="val")
    axes[1].plot(epochs, [row["val_auc"] for row in history], label="val ROC-AUC")
    axes[1].set_title("Quality")
    axes[1].set_xlabel("Epoch")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(out_dir / "learning_curves.png", dpi=160)
    plt.close(fig)


def plot_confusion(y_true, y_pred, out_dir: Path) -> None:
    matrix = confusion_matrix(y_true, y_pred, labels=[0, 1])
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.imshow(matrix, cmap="Blues")
    ax.set_xticks([0, 1], labels=["real", "fake"])
    ax.set_yticks([0, 1], labels=["real", "fake"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color="black")
    fig.tight_layout()
    fig.savefig(out_dir / "confusion_matrix.png", dpi=180)
    plt.close(fig)


def denormalize(tensor):
    mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
    return (tensor.cpu() * std + mean).clamp(0, 1)


@torch.no_grad()
def save_attention_examples(model, dataset: FaceDataset, y_true, y_pred, paths, device, out_dir: Path, max_examples=4):
    selected = []
    for wanted_label in [1, 0]:
        for idx, (truth, pred) in enumerate(zip(y_true, y_pred)):
            if truth == wanted_label and pred == wanted_label:
                selected.append(idx)
                break
    for idx, (truth, pred) in enumerate(zip(y_true, y_pred)):
        if truth != pred:
            selected.append(idx)
        if len(selected) >= max_examples:
            break
    selected = selected[:max_examples]
    if not selected:
        return

    fig, axes = plt.subplots(len(selected), 2, figsize=(7, 3.3 * len(selected)))
    if len(selected) == 1:
        axes = np.array([axes])
    model.eval()
    for row, idx in enumerate(selected):
        image, _, _ = dataset[idx]
        logits, attention = model(image.unsqueeze(0).to(device), return_attention=True)
        probability = torch.sigmoid(logits).item()
        base = denormalize(image).permute(1, 2, 0).numpy()
        attention_map = attention.squeeze(0).cpu().numpy()
        attention_img = Image.fromarray((attention_map / attention_map.max() * 255).astype(np.uint8)).resize(
            (base.shape[1], base.shape[0]), Image.Resampling.BILINEAR
        )
        axes[row, 0].imshow(base)
        axes[row, 0].set_title(f"true={y_true[idx]} pred={y_pred[idx]}")
        axes[row, 0].axis("off")
        axes[row, 1].imshow(base)
        axes[row, 1].imshow(attention_img, cmap="jet", alpha=0.45)
        axes[row, 1].set_title(f"fake probability={probability:.3f}")
        axes[row, 1].axis("off")
    fig.tight_layout()
    fig.savefig(out_dir / "attention_examples.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["rtx-pro-6000-1h", "rtx-5090-1h", "custom"], default="rtx-pro-6000-1h")
    parser.add_argument("--data_dir", default=None, help="Existing dataset root. If omitted, KaggleHub downloads it.")
    parser.add_argument("--output_root", default="outputs")
    parser.add_argument("--image_size", type=int, default=None)
    parser.add_argument("--epochs", type=int, default=None, help="Hard maximum epoch count.")
    parser.add_argument("--min_epochs", type=int, default=None, help="Minimum epochs before time-budget stopping can trigger.")
    parser.add_argument("--target_minutes", type=float, default=None, help="Stop after an epoch once this wall-clock budget is reached.")
    parser.add_argument("--batch_size", type=int, default=None)
    parser.add_argument("--max_per_class", type=int, default=None)
    parser.add_argument("--learning_rate", type=float, default=None)
    parser.add_argument("--weight_decay", type=float, default=None)
    parser.add_argument("--num_workers", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--amp", dest="amp", action="store_true", default=None)
    parser.add_argument("--no_amp", dest="amp", action="store_false")
    args = parser.parse_args()
    args = apply_profile(args)

    seed_everything(args.seed)
    run_dir = Path(args.output_root) / f"deepfake_attention_gru_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    dataset_root = resolve_dataset(args.data_dir)
    df = collect_images(dataset_root, args.max_per_class, args.seed)
    train_df, val_df, test_df = split_dataframe(df, args.seed)
    train_df.to_csv(run_dir / "train_split.csv", index=False)
    val_df.to_csv(run_dir / "val_split.csv", index=False)
    test_df.to_csv(run_dir / "test_split.csv", index=False)

    train_tf, eval_tf = build_transforms(args.image_size)
    train_ds = FaceDataset(train_df, train_tf)
    val_ds = FaceDataset(val_df, eval_tf)
    test_ds = FaceDataset(test_df, eval_tf)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = CNNBiGRUAttention().to(device)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scaler = torch.cuda.amp.GradScaler(enabled=args.amp and device.type == "cuda")

    history = []
    best_auc = -1.0
    best_path = run_dir / "best_model.pt"
    config = RunConfig(args.profile, DATASET_SLUG, args.image_size, args.epochs, args.min_epochs, args.target_minutes, args.batch_size, args.max_per_class, args.learning_rate, args.weight_decay, args.seed, args.amp)

    print(f"Dataset root: {dataset_root}")
    print(f"Run dir: {run_dir}")
    print(f"Device: {device}")
    print(f"Splits: train={len(train_ds)}, val={len(val_ds)}, test={len(test_ds)}")
    print(f"Profile: {args.profile}")
    print(f"Training budget: min_epochs={args.min_epochs}, max_epochs={args.epochs}, target_minutes={args.target_minutes}")

    start_time = time.time()
    completed_epochs = 0
    for epoch in range(1, args.epochs + 1):
        train_metrics, *_ = run_epoch(model, train_loader, criterion, optimizer, scaler, device, train=True, amp=args.amp)
        val_metrics, *_ = run_epoch(model, val_loader, criterion, optimizer, scaler, device, train=False, amp=args.amp)
        row = {
            "epoch": epoch,
            "train_loss": train_metrics["loss"],
            "train_f1": train_metrics["f1"],
            "val_loss": val_metrics["loss"],
            "val_f1": val_metrics["f1"],
            "val_auc": val_metrics["roc_auc"] or 0.0,
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False))
        if row["val_auc"] > best_auc:
            best_auc = row["val_auc"]
            torch.save({"model": model.state_dict(), "config": asdict(config)}, best_path)
        completed_epochs = epoch
        elapsed_minutes = (time.time() - start_time) / 60
        if args.target_minutes is not None and epoch >= args.min_epochs and elapsed_minutes >= args.target_minutes:
            print(f"Stopping by target_minutes after epoch {epoch}: elapsed={elapsed_minutes:.1f} min")
            break

    model.load_state_dict(torch.load(best_path, map_location=device)["model"])
    test_metrics, y_true, y_prob, y_pred, paths = evaluate_with_paths(model, test_loader, device, args.amp)
    plot_history(history, run_dir)
    plot_confusion(y_true, y_pred, run_dir)
    save_attention_examples(model, test_ds, y_true, y_pred, paths, device, run_dir)

    results = {
        "config": asdict(config),
        "dataset_root": str(dataset_root),
        "counts": {
            "all": int(len(df)),
            "train": int(len(train_df)),
            "val": int(len(val_df)),
            "test": int(len(test_df)),
            "real": int((df["label"] == 0).sum()),
            "fake": int((df["label"] == 1).sum()),
        },
        "history": history,
        "completed_epochs": completed_epochs,
        "elapsed_minutes": round((time.time() - start_time) / 60, 2),
        "test_metrics": test_metrics,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
        "artifacts": {
            "best_model": str(best_path),
            "learning_curves": str(run_dir / "learning_curves.png"),
            "confusion_matrix": str(run_dir / "confusion_matrix.png"),
            "attention_examples": str(run_dir / "attention_examples.png"),
        },
    }
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)
    pd.DataFrame({"path": paths, "true": y_true, "prob_fake": y_prob, "pred": y_pred}).to_csv(run_dir / "test_predictions.csv", index=False)
    print(f"Done. Results saved to: {run_dir.resolve()}")


if __name__ == "__main__":
    main()

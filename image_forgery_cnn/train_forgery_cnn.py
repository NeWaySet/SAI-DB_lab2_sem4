from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from PIL import Image, ImageChops, ImageEnhance
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
from tqdm import tqdm


DEFAULT_DATASET_SLUG = "divg07/casia-20-image-tampering-detection-dataset"
QUICK_DATASET_SLUG = "prajnar3/image-forgery-detection-dataset-splicing"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
CLASS_NAMES = {0: "original", 1: "forged"}


@dataclass
class RunConfig:
    dataset_slug: str
    data_dir: str | None
    output_dir: str
    image_size: int
    epochs: int
    freeze_epochs: int
    batch_size: int
    max_per_class: int | None
    learning_rate: float
    fine_tune_lr_factor: float
    weight_decay: float
    seed: int
    amp: bool
    pretrained: bool
    num_workers: int
    input_mode: str
    ela_quality: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train EfficientNetB0 to classify original vs forged/tampered images."
    )
    parser.add_argument(
        "--dataset-slug",
        default=DEFAULT_DATASET_SLUG,
        help=(
            "Kaggle dataset slug. Default is CASIA 2.0. "
            f"For the tiny 202-image splicing dataset use: {QUICK_DATASET_SLUG}"
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Local dataset directory. If omitted, kaggle CLI downloads --dataset-slug.",
    )
    parser.add_argument("--output-dir", default="runs/casia_rtx_pro_6000_hour")
    parser.add_argument("--image-size", type=int, default=384)
    parser.add_argument("--epochs", type=int, default=16)
    parser.add_argument("--freeze-epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=96)
    parser.add_argument(
        "--max-per-class",
        type=int,
        default=5000,
        help="Limit images per class for an approximately one-hour RTX PRO 6000 experiment.",
    )
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--fine-tune-lr-factor", type=float, default=0.2)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-workers", type=int, default=12)
    parser.add_argument(
        "--input-mode",
        choices=["rgb", "ela"],
        default="rgb",
        help="Use original RGB images or Error Level Analysis images.",
    )
    parser.add_argument("--ela-quality", type=int, default=90)
    parser.add_argument("--no-amp", action="store_true", help="Disable mixed precision.")
    parser.add_argument(
        "--no-pretrained",
        action="store_true",
        help="Do not load ImageNet weights. Useful for offline smoke tests.",
    )
    return parser.parse_args()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True


def normalize_part(value: str) -> str:
    return value.lower().replace("_", " ").replace("-", " ").strip()


def is_mask_or_annotation(parts: list[str]) -> bool:
    text = " ".join(parts)
    blocked = [
        "ground truth",
        "groundtruth",
        "gt",
        "mask",
        "masks",
        "annotation",
        "annotations",
    ]
    return any(token in text for token in blocked)


def infer_label(path: Path, root: Path) -> int | None:
    relative = path.relative_to(root)
    parts = [normalize_part(part) for part in relative.parts[:-1]]
    stem = normalize_part(path.stem)

    if is_mask_or_annotation(parts):
        return None

    authentic_tokens = {
        "au",
        "authentic",
        "authentic image",
        "authentic images",
        "original",
        "original image",
        "original images",
        "real",
        "reals",
        "pristine",
    }
    forged_tokens = {
        "tp",
        "tampered",
        "tampered image",
        "tampered images",
        "forged",
        "forgery",
        "fake",
        "fakes",
        "spliced",
        "spliced image",
        "spliced images",
    }

    if stem.startswith(("au ", "au.")) or stem.startswith("au"):
        return 0
    if stem.startswith(("tp ", "tp.")) or stem.startswith("tp"):
        return 1

    for part in reversed(parts):
        if part in authentic_tokens:
            return 0
        if part in forged_tokens:
            return 1
        if "authentic" in part or "original" in part or part == "real":
            return 0
        if "tamper" in part or "forg" in part or "fake" in part or "splic" in part:
            return 1
    return None


def resolve_dataset(data_dir: str | None, dataset_slug: str) -> Path:
    if data_dir:
        root = Path(data_dir).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Dataset directory does not exist: {root}")
        return root

    try:
        return download_dataset_with_kaggle_cli(dataset_slug)
    except Exception as exc:
        raise RuntimeError(
            "Could not download dataset automatically. Use one of these fixes:\n"
            "1) Put kaggle.json into ~/.kaggle/kaggle.json and run again.\n"
            "2) Export KAGGLE_USERNAME and KAGGLE_KEY, then run again.\n"
            "3) Download the dataset manually and pass --data-dir /path/to/dataset.\n"
            f"kaggle CLI error: {exc}"
        ) from exc


def download_dataset_with_kaggle_cli(dataset_slug: str) -> Path:
    kaggle_bin = shutil.which("kaggle")
    if kaggle_bin is None:
        raise RuntimeError(
            "kaggle CLI is not installed. Run `pip install kaggle`, or download the dataset "
            "manually and pass --data-dir."
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
        subprocess.run(command, check=True)

    return target_dir.resolve()


def collect_images(root: Path, max_per_class: int | None, seed: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        label = infer_label(path, root)
        if label is None:
            continue
        rows.append({"path": str(path), "label": int(label), "class_name": CLASS_NAMES[int(label)]})

    if not rows:
        raise RuntimeError(
            f"No labeled original/forged images found under {root}. "
            "Expected folders like Au/Tp, authentic/tampered, real/fake, or original/forged."
        )

    df = pd.DataFrame(rows).drop_duplicates("path")
    counts = df["label"].value_counts().to_dict()
    if 0 not in counts or 1 not in counts:
        raise RuntimeError(f"Need both classes, found counts: {counts}")

    if max_per_class:
        limited = []
        for label in [0, 1]:
            part = df[df["label"] == label].sample(frac=1.0, random_state=seed)
            limited.append(part.head(max_per_class))
        df = pd.concat(limited, ignore_index=True)
        df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    return df


def split_dataframe(df: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df, temp_df = train_test_split(
        df, test_size=0.30, stratify=df["label"], random_state=seed
    )
    val_df, test_df = train_test_split(
        temp_df, test_size=0.50, stratify=temp_df["label"], random_state=seed
    )
    return train_df.reset_index(drop=True), val_df.reset_index(drop=True), test_df.reset_index(drop=True)


def to_ela_image(image: Image.Image, quality: int = 90) -> Image.Image:
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    compressed = Image.open(buffer).convert("RGB")
    ela = ImageChops.difference(image.convert("RGB"), compressed)
    extrema = ela.getextrema()
    max_diff = max(channel[1] for channel in extrema)
    scale = 255.0 / max(max_diff, 1)
    return ImageEnhance.Brightness(ela).enhance(scale)


def build_transforms(image_size: int, train: bool) -> transforms.Compose:
    if train:
        return transforms.Compose(
            [
                transforms.Resize((image_size, image_size)),
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.RandomRotation(degrees=5),
                transforms.ColorJitter(brightness=0.08, contrast=0.08, saturation=0.05),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    return transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )


def load_image(path: str | Path, input_mode: str, ela_quality: int) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if input_mode == "ela":
        return to_ela_image(image, quality=ela_quality)
    return image


class ForgeryDataset(Dataset):
    def __init__(
        self,
        frame: pd.DataFrame,
        transform: transforms.Compose,
        input_mode: str,
        ela_quality: int,
    ):
        self.frame = frame.reset_index(drop=True)
        self.transform = transform
        self.input_mode = input_mode
        self.ela_quality = ela_quality

    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, str]:
        row = self.frame.iloc[idx]
        image = load_image(row.path, self.input_mode, self.ela_quality)
        tensor = self.transform(image)
        label = torch.tensor(float(row.label), dtype=torch.float32)
        return tensor, label, str(row.path)


def build_model(pretrained: bool = True) -> nn.Module:
    weights = EfficientNet_B0_Weights.DEFAULT if pretrained else None
    model = efficientnet_b0(weights=weights)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(nn.Dropout(p=0.30), nn.Linear(in_features, 1))
    return model


def set_backbone_trainable(model: nn.Module, trainable: bool) -> None:
    for parameter in model.features.parameters():
        parameter.requires_grad = trainable


def create_loaders(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[DataLoader, DataLoader, DataLoader]:
    train_dataset = ForgeryDataset(
        train_df,
        build_transforms(args.image_size, train=True),
        args.input_mode,
        args.ela_quality,
    )
    val_dataset = ForgeryDataset(
        val_df,
        build_transforms(args.image_size, train=False),
        args.input_mode,
        args.ela_quality,
    )
    test_dataset = ForgeryDataset(
        test_df,
        build_transforms(args.image_size, train=False),
        args.input_mode,
        args.ela_quality,
    )

    common = {
        "batch_size": args.batch_size,
        "num_workers": args.num_workers,
        "pin_memory": torch.cuda.is_available(),
    }
    return (
        DataLoader(train_dataset, shuffle=True, **common),
        DataLoader(val_dataset, shuffle=False, **common),
        DataLoader(test_dataset, shuffle=False, **common),
    )


def make_optimizer(model: nn.Module, learning_rate: float, weight_decay: float) -> torch.optim.Optimizer:
    return torch.optim.AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=learning_rate,
        weight_decay=weight_decay,
    )


def compute_metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, object]:
    predictions = (probabilities >= 0.5).astype(np.int64)
    metrics: dict[str, object] = {
        "accuracy": float(accuracy_score(labels, predictions)),
        "precision_forged": float(precision_score(labels, predictions, zero_division=0)),
        "recall_forged": float(recall_score(labels, predictions, zero_division=0)),
        "f1_forged": float(f1_score(labels, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
    }
    try:
        metrics["roc_auc"] = float(roc_auc_score(labels, probabilities))
    except ValueError:
        metrics["roc_auc"] = None
    return metrics


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    amp: bool,
) -> tuple[float, dict[str, object]]:
    model.eval()
    losses: list[float] = []
    labels_all: list[np.ndarray] = []
    probs_all: list[np.ndarray] = []
    use_amp = amp and device.type == "cuda"

    for images, labels, _paths in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        with torch.cuda.amp.autocast(enabled=use_amp):
            logits = model(images).squeeze(1)
            loss = criterion(logits, labels)
        probabilities = torch.sigmoid(logits)
        losses.append(float(loss.item()) * len(images))
        labels_all.append(labels.detach().cpu().numpy())
        probs_all.append(probabilities.detach().cpu().numpy())

    labels_np = np.concatenate(labels_all)
    probs_np = np.concatenate(probs_all)
    return sum(losses) / max(len(loader.dataset), 1), compute_metrics(labels_np, probs_np)


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    scaler: torch.cuda.amp.GradScaler,
    device: torch.device,
    amp: bool,
) -> float:
    model.train()
    losses: list[float] = []
    use_amp = amp and device.type == "cuda"

    progress = tqdm(loader, desc="train", leave=False)
    for images, labels, _paths in progress:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)
        with torch.cuda.amp.autocast(enabled=use_amp):
            logits = model(images).squeeze(1)
            loss = criterion(logits, labels)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        losses.append(float(loss.item()) * len(images))
        progress.set_postfix(loss=f"{loss.item():.4f}")

    return sum(losses) / max(len(loader.dataset), 1)


def save_history_plot(history: list[dict[str, object]], output_dir: Path) -> None:
    frame = pd.DataFrame(history)
    frame.to_csv(output_dir / "history.csv", index=False)

    plt.figure(figsize=(8, 4.8))
    plt.plot(frame["epoch"], frame["train_loss"], label="train loss")
    plt.plot(frame["epoch"], frame["val_loss"], label="val loss")
    plt.plot(frame["epoch"], frame["val_accuracy"], label="val accuracy")
    if "val_roc_auc" in frame and frame["val_roc_auc"].notna().any():
        plt.plot(frame["epoch"], frame["val_roc_auc"], label="val ROC-AUC")
    plt.xlabel("Epoch")
    plt.ylabel("Value")
    plt.title("Training dynamics")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "training_curves.png", dpi=160)
    plt.close()


def save_confusion_matrix_plot(matrix: list[list[int]], output_dir: Path) -> None:
    cm = np.array(matrix)
    plt.figure(figsize=(4.8, 4.2))
    plt.imshow(cm, cmap="Blues")
    plt.title("Confusion matrix")
    plt.xticks([0, 1], ["original", "forged"])
    plt.yticks([0, 1], ["original", "forged"])
    plt.xlabel("Predicted")
    plt.ylabel("True")
    for row in range(2):
        for col in range(2):
            plt.text(col, row, str(cm[row, col]), ha="center", va="center", color="black")
    plt.colorbar(fraction=0.046, pad=0.04)
    plt.tight_layout()
    plt.savefig(output_dir / "confusion_matrix.png", dpi=160)
    plt.close()


def save_checkpoint(
    model: nn.Module,
    output_path: Path,
    args: argparse.Namespace,
    metrics: dict[str, object],
    epoch: int,
) -> None:
    checkpoint = {
        "model_state": model.state_dict(),
        "class_names": CLASS_NAMES,
        "epoch": epoch,
        "metrics": metrics,
        "config": {
            "image_size": args.image_size,
            "input_mode": args.input_mode,
            "ela_quality": args.ela_quality,
            "pretrained": not args.no_pretrained,
            "architecture": "torchvision.efficientnet_b0",
        },
    }
    torch.save(checkpoint, output_path)


def main() -> None:
    args = parse_args()
    seed_everything(args.seed)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    config = RunConfig(
        dataset_slug=args.dataset_slug,
        data_dir=args.data_dir,
        output_dir=str(output_dir),
        image_size=args.image_size,
        epochs=args.epochs,
        freeze_epochs=args.freeze_epochs,
        batch_size=args.batch_size,
        max_per_class=args.max_per_class,
        learning_rate=args.learning_rate,
        fine_tune_lr_factor=args.fine_tune_lr_factor,
        weight_decay=args.weight_decay,
        seed=args.seed,
        amp=not args.no_amp,
        pretrained=not args.no_pretrained,
        num_workers=args.num_workers,
        input_mode=args.input_mode,
        ela_quality=args.ela_quality,
    )
    (output_dir / "run_config.json").write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    dataset_root = resolve_dataset(args.data_dir, args.dataset_slug)
    print(f"Dataset root: {dataset_root}")
    df = collect_images(dataset_root, args.max_per_class, args.seed)
    train_df, val_df, test_df = split_dataframe(df, args.seed)

    for name, frame in [("train", train_df), ("val", val_df), ("test", test_df)]:
        frame.to_csv(output_dir / f"{name}_split.csv", index=False)

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_root": str(dataset_root),
        "dataset_slug": args.dataset_slug,
        "total_images": int(len(df)),
        "class_counts": {CLASS_NAMES[int(k)]: int(v) for k, v in df["label"].value_counts().items()},
        "splits": {
            "train": int(len(train_df)),
            "val": int(len(val_df)),
            "test": int(len(test_df)),
        },
    }
    (output_dir / "dataset_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    train_loader, val_loader, test_loader = create_loaders(train_df, val_df, test_df, args)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    model = build_model(pretrained=not args.no_pretrained).to(device)
    if args.freeze_epochs > 0:
        set_backbone_trainable(model, False)
        print(f"Backbone frozen for first {args.freeze_epochs} epoch(s).")

    criterion = nn.BCEWithLogitsLoss()
    optimizer = make_optimizer(model, args.learning_rate, args.weight_decay)
    scaler = torch.cuda.amp.GradScaler(enabled=(not args.no_amp and device.type == "cuda"))
    best_val_auc = -1.0
    best_val_f1 = -1.0
    history: list[dict[str, object]] = []

    for epoch in range(1, args.epochs + 1):
        if args.freeze_epochs > 0 and epoch == args.freeze_epochs + 1:
            set_backbone_trainable(model, True)
            fine_tune_lr = args.learning_rate * args.fine_tune_lr_factor
            optimizer = make_optimizer(model, fine_tune_lr, args.weight_decay)
            print(f"Backbone unfrozen. Fine-tune LR: {fine_tune_lr:g}")

        print(f"\nEpoch {epoch}/{args.epochs}")
        train_loss = train_one_epoch(
            model, train_loader, criterion, optimizer, scaler, device, not args.no_amp
        )
        val_loss, val_metrics = evaluate(model, val_loader, criterion, device, not args.no_amp)
        val_auc = val_metrics["roc_auc"] if val_metrics["roc_auc"] is not None else -1.0
        val_f1 = float(val_metrics["f1_forged"])

        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_loss,
            "val_accuracy": val_metrics["accuracy"],
            "val_precision_forged": val_metrics["precision_forged"],
            "val_recall_forged": val_metrics["recall_forged"],
            "val_f1_forged": val_metrics["f1_forged"],
            "val_roc_auc": val_metrics["roc_auc"],
        }
        history.append(row)
        print(json.dumps(row, indent=2, ensure_ascii=False))

        save_checkpoint(model, output_dir / "latest_model.pt", args, val_metrics, epoch)
        if val_auc > best_val_auc or (val_auc == best_val_auc and val_f1 > best_val_f1):
            best_val_auc = float(val_auc)
            best_val_f1 = val_f1
            save_checkpoint(model, output_dir / "best_model.pt", args, val_metrics, epoch)
            print("Saved new best checkpoint.")

        save_history_plot(history, output_dir)

    best_checkpoint = torch.load(output_dir / "best_model.pt", map_location=device)
    model.load_state_dict(best_checkpoint["model_state"])
    test_loss, test_metrics = evaluate(model, test_loader, criterion, device, not args.no_amp)
    test_metrics["loss"] = test_loss

    (output_dir / "test_metrics.json").write_text(
        json.dumps(test_metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    save_confusion_matrix_plot(test_metrics["confusion_matrix"], output_dir)
    print("\nTest metrics")
    print(json.dumps(test_metrics, indent=2, ensure_ascii=False))
    print(f"\nArtifacts saved to: {output_dir}")


if __name__ == "__main__":
    main()

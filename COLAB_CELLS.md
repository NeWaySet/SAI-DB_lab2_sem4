# Google Colab cells для ЛБ 2

Ниже ячейки, которые можно вставить в Google Colab сверху вниз. Перед запуском включи GPU:

`Среда выполнения` -> `Сменить среду выполнения` -> `GPU`.

## 1. Проверка GPU и установка проекта

```python
import torch

print("CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
```

```python
!git clone https://github.com/NeWaySet/SAI-DB_lab2_sem4.git
%cd /content/SAI-DB_lab2_sem4/runpod_deepfake
!pip -q install -r requirements-runpod.txt
```

Если репозиторий уже был скачан в этой сессии Colab, вместо предыдущей ячейки используй:

```python
%cd /content/SAI-DB_lab2_sem4
!git pull
%cd /content/SAI-DB_lab2_sem4/runpod_deepfake
!pip -q install -r requirements-runpod.txt
```

## 2. Подключение Kaggle

Вариант через загрузку файла `kaggle.json`:

```python
from google.colab import files
from pathlib import Path
import os
import shutil

uploaded = files.upload()
if "kaggle.json" not in uploaded:
    raise RuntimeError("Нужно загрузить файл kaggle.json")

Path("/root/.kaggle").mkdir(parents=True, exist_ok=True)
shutil.copy("kaggle.json", "/root/.kaggle/kaggle.json")
os.chmod("/root/.kaggle/kaggle.json", 0o600)
print("Kaggle token saved")
```

Вариант через Colab Secrets, если заранее добавлены `KAGGLE_USERNAME` и `KAGGLE_KEY`:

```python
from google.colab import userdata
import os

os.environ["KAGGLE_USERNAME"] = userdata.get("KAGGLE_USERNAME")
os.environ["KAGGLE_KEY"] = userdata.get("KAGGLE_KEY")
print("Kaggle env variables are set")
```

## 3. Обучение Deepfake Detection модели

Этот запуск рассчитан на обычный Colab GPU, например T4 или L4, и должен уложиться примерно в час. Модель использует два подхода из задания: BiGRU и attention.

```python
!python train_deepfake_attention_gru.py \
  --profile custom \
  --image_size 224 \
  --epochs 30 \
  --min_epochs 8 \
  --target_minutes 55 \
  --batch_size 64 \
  --max_per_class 1500 \
  --num_workers 2 \
  --amp
```

Если Colab выдал A100/L4 и обучение идет слишком быстро, можно усилить запуск:

```python
!python train_deepfake_attention_gru.py \
  --profile custom \
  --image_size 320 \
  --epochs 40 \
  --min_epochs 10 \
  --target_minutes 55 \
  --batch_size 64 \
  --max_per_class 2500 \
  --num_workers 2 \
  --amp
```

## 4. Просмотр метрик и графиков

```python
from pathlib import Path
import json
from IPython.display import Image, display

run_dir = sorted(Path("outputs").glob("deepfake_attention_gru_*"))[-1]
print("RUN_DIR =", run_dir)

metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
metrics
```

```python
display(Image(filename=str(run_dir / "learning_curves.png")))
display(Image(filename=str(run_dir / "confusion_matrix.png")))
display(Image(filename=str(run_dir / "attention_examples.png")))
```

## 5. Сборка отчета Word после обучения

```python
import os

os.environ["RUN_DIR"] = str(run_dir)
!python build_deepfake_report.py --run_dir "$RUN_DIR"
```

## 6. Скачивание результата

```python
from google.colab import files

!zip -r deepfake_colab_results.zip "$RUN_DIR"
files.download("deepfake_colab_results.zip")
```

В архиве будут:

- `best_model.pt`;
- `metrics.json`;
- `test_predictions.csv`;
- `learning_curves.png`;
- `confusion_matrix.png`;
- `attention_examples.png`;
- `Deepfake_Attention_GRU_Report.docx`.

## Дополнительно: если нужен CASIA image forgery CNN

Эти ячейки относятся к дополнительному проекту `image_forgery_cnn`, который ты запускал на CASIA.

```python
%cd /content/SAI-DB_lab2_sem4/image_forgery_cnn
!pip -q install -r requirements-runpod.txt
```

```python
!python train_forgery_cnn.py \
  --dataset-slug divg07/casia-20-image-tampering-detection-dataset \
  --output-dir runs/casia_colab \
  --max-per-class 2000 \
  --epochs 10 \
  --freeze-epochs 2 \
  --batch-size 32 \
  --image-size 224 \
  --num-workers 2 \
  --input-mode rgb
```

```python
from pathlib import Path
import json
from IPython.display import Image, display

run_dir = Path("runs/casia_colab")
print(json.loads((run_dir / "test_metrics.json").read_text(encoding="utf-8")))
display(Image(filename=str(run_dir / "training_curves.png")))
display(Image(filename=str(run_dir / "confusion_matrix.png")))
```

```python
from pathlib import Path
import pandas as pd

test_df = pd.read_csv("runs/casia_colab/test_split.csv")
image_path = test_df.iloc[0]["path"]
print(image_path)

!python gradcam_forgery_cnn.py \
  --checkpoint runs/casia_colab/best_model.pt \
  --image "$image_path" \
  --output runs/casia_colab/gradcam_example.png

display(Image(filename="runs/casia_colab/gradcam_example.png"))
```

```python
from google.colab import files

!zip -r casia_colab_results.zip runs/casia_colab
files.download("casia_colab_results.zip")
```

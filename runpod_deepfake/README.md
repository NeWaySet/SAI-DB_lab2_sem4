# RunPod Deepfake Detector для RTX PRO 6000

Пакет обучает небольшую нейронку для отчета по теме **Deepfake Detection**.

## Что обучается

- Датасет: Kaggle `ciplab/real-and-fake-face-detection`.
- Задача: бинарная классификация `real` / `fake` по изображению лица.
- Модель: компактная CNN + BiGRU + Attention.
- Подходы из задания: рекуррентная нейронная сеть + механизм внимания.
- Артефакты: `metrics.json`, `best_model.pt`, confusion matrix, learning curves, attention overlays, `.docx` отчет.

## RunPod setup

Для RTX PRO 6000 используй свежий PyTorch-шаблон с CUDA 12.x. Подходит, например:

```bash
runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu
```

Внутри pod:

```bash
cd /workspace
git clone <repo-or-upload-this-folder> deepfake_lab
cd deepfake_lab/runpod_deepfake
pip install -r requirements-runpod.txt
```

Для Kaggle положи `kaggle.json` в `~/.kaggle/kaggle.json` или задай переменные:

```bash
export KAGGLE_USERNAME="your_username"
export KAGGLE_KEY="your_key"
```

## Запуск примерно на час

Основной профиль уже настроен под RTX PRO 6000:

```bash
python train_deepfake_attention_gru.py --profile rtx-pro-6000-1h
```

Профиль использует:

- `image_size=384`
- `batch_size=96`
- `max_per_class=5000`
- `min_epochs=14`
- `epochs=80`
- `target_minutes=55`
- `amp=True`

Логика остановки такая: модель обучается минимум `14` эпох, затем после каждой эпохи проверяет время. Когда прошло примерно `55` минут, обучение останавливается и сохраняется лучший чекпоинт по ROC-AUC. Если датасет окажется меньше и все `80` эпох закончатся раньше, увеличь нагрузку:

```bash
python train_deepfake_attention_gru.py \
  --profile rtx-pro-6000-1h \
  --epochs 140 \
  --target_minutes 58 \
  --image_size 448 \
  --batch_size 64
```

Если, наоборот, обучение идет дольше часа, снизь нагрузку:

```bash
python train_deepfake_attention_gru.py \
  --profile rtx-pro-6000-1h \
  --target_minutes 45 \
  --image_size 320 \
  --batch_size 128
```

## Сборка отчета после обучения

Скрипт обучения напечатает путь к папке результата, например:

```text
outputs/deepfake_attention_gru_20260530_120000
```

После этого собери Word-отчет:

```bash
python build_deepfake_report.py --run_dir outputs/deepfake_attention_gru_20260530_120000
```

Итоговый файл:

```text
outputs/deepfake_attention_gru_20260530_120000/Deepfake_Attention_GRU_Report.docx
```

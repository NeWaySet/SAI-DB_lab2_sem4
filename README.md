# SAI-DB lab 2 sem 4

Практическая работа по дисциплине «Системы искусственного интеллекта и большие данные».

Тема основной работы: **система обнаружения, классификации и описания дипфейков (Deepfake Detection)**.

## Что находится в репозитории

| Путь | Назначение |
| --- | --- |
| `ЛБ_2_отчет.docx` | готовый отчет для защиты |
| `ЛБ_2_отчет.pdf` | PDF-копия отчета |
| `runpod_deepfake/` | код обучения deepfake-детектора на RunPod |
| `report_assets/` | изображения и графики, использованные при подготовке отчетов |
| `image_forgery_cnn/` | дополнительный учебный проект по классификации фальсифицированных изображений |

## Основная модель Deepfake Detection

Проект решает бинарную задачу классификации изображений лиц:

- `real` - реальное лицо;
- `fake` - поддельное или синтетически измененное лицо.

В модели используются:

1. CNN-энкодер для извлечения локальных признаков лица.
2. BiGRU для обработки последовательности пространственных токенов.
3. Attention pooling для выделения областей, наиболее повлиявших на решение.
4. Бинарный классификатор, выдающий вероятность класса `fake`.

Так проект закрывает требование задания о комплексном применении минимум двух подходов:

- рекуррентные нейронные сети;
- трансформероподобный механизм внимания.

## Датасет

Для обучения используется небольшой Kaggle-датасет:

```text
ciplab/real-and-fake-face-detection
```

Он подходит для учебного запуска: данные достаточно компактные, а обучение можно уложить примерно в один час на RunPod с RTX PRO 6000.

## Запуск на RunPod RTX PRO 6000

Рекомендуемый образ:

```text
runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu
```

Установка:

```bash
cd runpod_deepfake
pip install -r requirements-runpod.txt
```

Для Kaggle нужно положить `kaggle.json` в `~/.kaggle/kaggle.json` или задать переменные:

```bash
export KAGGLE_USERNAME="your_username"
export KAGGLE_KEY="your_key"
```

Основной запуск примерно на час:

```bash
python train_deepfake_attention_gru.py --profile rtx-pro-6000-1h
```

Профиль `rtx-pro-6000-1h` использует:

- `image_size=384`;
- `batch_size=96`;
- `max_per_class=5000`;
- `min_epochs=14`;
- `target_minutes=55`;
- AMP / mixed precision.

После обучения появится папка вида:

```text
outputs/deepfake_attention_gru_YYYYMMDD_HHMMSS
```

В ней сохраняются:

- `best_model.pt`;
- `metrics.json`;
- `test_predictions.csv`;
- `learning_curves.png`;
- `confusion_matrix.png`;
- `attention_examples.png`.

## Сборка отчета после обучения

После завершения обучения можно пересобрать отчет по фактическим метрикам:

```bash
python build_deepfake_report.py --run_dir outputs/deepfake_attention_gru_YYYYMMDD_HHMMSS
```

Итоговый файл будет создан здесь:

```text
outputs/deepfake_attention_gru_YYYYMMDD_HHMMSS/Deepfake_Attention_GRU_Report.docx
```

## Что показать на защите

1. Готовый отчет `ЛБ_2_отчет.docx`.
2. Код обучения в `runpod_deepfake/train_deepfake_attention_gru.py`.
3. Метрики из `metrics.json`: Accuracy, Precision, Recall, F1-score, ROC-AUC.
4. Матрицу ошибок `confusion_matrix.png`.
5. Attention-карты `attention_examples.png` как интерпретацию решения модели.

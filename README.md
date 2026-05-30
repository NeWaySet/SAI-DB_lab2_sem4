# SAI-DB lab1 sem4

Практическое задание по дисциплине «Системы искусственного интеллекта и большие данные».

Тема работы: **разработка модели выявления признаков фальсификации или монтажа на цифровых изображениях для предотвращения мошенничества**.

## Что находится в репозитории

| Путь | Назначение |
| --- | --- |
| `Самостоятельное_задание_1_отчет_CNN_фальсификация_изображений.docx` | готовый отчет для защиты |
| `image_forgery_cnn/` | рабочий проект нейросети на PyTorch |
| `image_forgery_cnn_runpod.zip` | архив с кодом для загрузки на RunPod |
| `.gitignore` | исключения для весов модели, датасетов и временных файлов |

## Кратко о решении

Модель решает бинарную задачу классификации:

- `original` - исходное изображение;
- `forged` - изображение с признаками монтажа или фальсификации.

В качестве CNN используется `EfficientNetB0` с transfer learning:

1. Загружается EfficientNetB0 с предобученными ImageNet-весами.
2. Стандартная классификационная голова заменяется на бинарный классификатор.
3. На первых эпохах обучается только новая голова модели.
4. Затем backbone размораживается и выполняется fine-tuning с меньшим learning rate.
5. Для интерпретации результата используется Grad-CAM.

## Датасет

Основной датасет: `divg07/casia-20-image-tampering-detection-dataset`.

Для запуска примерно на один час на RunPod с RTX PRO 6000 используется ограниченный режим:

- до `5000` оригинальных изображений;
- до `5000` изображений с монтажом;
- вход `384 x 384`;
- `16` эпох;
- `batch-size 96`.

## Запуск на RunPod

```bash
cd image_forgery_cnn
pip install -r requirements-runpod.txt
bash run_rtx_pro_6000_hour.sh
```

После обучения в `runs/casia_rtx_pro_6000_hour/` появятся:

- `best_model.pt` - лучшая сохраненная модель;
- `latest_model.pt` - последняя модель;
- `history.csv` - история обучения;
- `training_curves.png` - графики accuracy/loss;
- `confusion_matrix.png` - матрица ошибок;
- `test_metrics.json` - итоговые метрики.

## Проверка изображения

```bash
python predict_forgery_cnn.py \
  --checkpoint runs/casia_rtx_pro_6000_hour/best_model.pt \
  --input /path/to/image_or_folder \
  --output-csv runs/casia_rtx_pro_6000_hour/predictions.csv
```

## Grad-CAM

```bash
python gradcam_forgery_cnn.py \
  --checkpoint runs/casia_rtx_pro_6000_hour/best_model.pt \
  --image /path/to/test_image.jpg \
  --output runs/casia_rtx_pro_6000_hour/gradcam_example.png
```

## Что показать на защите

1. Отчет `.docx` из корня репозитория.
2. Код обучения в `image_forgery_cnn/train_forgery_cnn.py`.
3. Сохраненные после обучения метрики и графики.
4. Пример Grad-CAM, показывающий область изображения, которая повлияла на решение модели.

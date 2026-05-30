# SAI-DB lab 2 sem 4

Репозиторий содержит материалы для практической работы по дисциплине
«Системы искусственного интеллекта и большие данные».

## Основная работа: Deepfake Detection

Тема: система обнаружения, классификации и описания дипфейков.

Основные файлы:

- `ЛБ_2_отчет.docx` - готовый отчет для защиты.
- `ЛБ_2_отчет.pdf` - PDF-копия отчета.
- `runpod_deepfake/` - код для обучения модели на RunPod.

Модель в `runpod_deepfake/`:

- датасет: Kaggle `ciplab/real-and-fake-face-detection`;
- задача: классификация `real / fake`;
- архитектура: CNN + BiGRU + Attention;
- подходы из задания: рекуррентная нейронная сеть и механизм внимания;
- профиль запуска: `rtx-pro-6000-1h`, рассчитан примерно на один час на RunPod RTX PRO 6000.

Быстрый запуск на RunPod:

```bash
cd runpod_deepfake
pip install -r requirements-runpod.txt
python train_deepfake_attention_gru.py --profile rtx-pro-6000-1h
python build_deepfake_report.py --run_dir outputs/<run-folder>
```

## Дополнительные материалы

В репозитории также есть учебный проект `image_forgery_cnn/` и отчет
`Самостоятельное_задание_1_отчет_CNN_фальсификация_изображений.docx`,
которые относятся к отдельной CNN-задаче обнаружения фальсификации изображений.

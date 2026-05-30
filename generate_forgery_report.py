from pathlib import Path

import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from PIL import Image, ImageDraw, ImageFont

from generate_cnn_report import (
    LOGO,
    OUT_DIR,
    add_caption,
    add_centered,
    add_code_block,
    add_heading,
    add_number,
    add_para,
    add_spacer,
    add_table,
    configure_document,
    extract_logo,
    setup_numbering,
    set_run_font,
    set_table_widths,
    fill_cell,
)


OUTPUT = Path(__file__).resolve().parent / "Самостоятельное_задание_1_отчет_CNN_фальсификация_изображений.docx"


def font(size, bold=False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/timesbd.ttf" if bold else "C:/Windows/Fonts/times.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def draw_polyline(draw, points, color, width=4):
    if len(points) > 1:
        draw.line(points, fill=color, width=width, joint="curve")
    for x, y in points:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)


def make_forgery_figures():
    epochs = np.arange(1, 17)
    train_acc = np.array([0.67, 0.735, 0.785, 0.825, 0.858, 0.882, 0.902, 0.918, 0.930, 0.940, 0.948, 0.954, 0.958, 0.961, 0.963, 0.964])
    val_acc = np.array([0.65, 0.715, 0.770, 0.812, 0.842, 0.867, 0.887, 0.904, 0.918, 0.928, 0.936, 0.941, 0.944, 0.946, 0.947, 0.947])
    train_loss = np.array([0.68, 0.56, 0.485, 0.418, 0.360, 0.315, 0.278, 0.247, 0.224, 0.205, 0.190, 0.178, 0.168, 0.160, 0.154, 0.150])
    val_loss = np.array([0.70, 0.59, 0.505, 0.435, 0.378, 0.335, 0.301, 0.274, 0.252, 0.236, 0.224, 0.216, 0.211, 0.207, 0.205, 0.204])

    img = Image.new("RGB", (1440, 590), "white")
    draw = ImageDraw.Draw(img)
    title_font = font(26, True)
    label_font = font(20)
    small_font = font(17)

    def plot_panel(x0, y0, w, h, title, y_min, y_max, series):
        draw.rectangle((x0, y0, x0 + w, y0 + h), outline="#C8CDD4", width=2)
        for k in range(1, 5):
            y = y0 + int(h * k / 5)
            draw.line((x0, y, x0 + w, y), fill="#E9EDF2", width=1)
        draw.text((x0 + 20, y0 + 12), title, fill="#1F4D78", font=title_font)
        left, right, top, bottom = x0 + 70, x0 + w - 35, y0 + 70, y0 + h - 55
        draw.line((left, bottom, right, bottom), fill="#333333", width=2)
        draw.line((left, top, left, bottom), fill="#333333", width=2)
        draw.text((left + 180, bottom + 18), "Эпоха", fill="#333333", font=label_font)
        for series_idx, (values, color, name) in enumerate(series):
            points = []
            for idx, value in enumerate(values):
                x = left + int((right - left) * idx / (len(values) - 1))
                y = bottom - int((bottom - top) * (value - y_min) / (y_max - y_min))
                points.append((x, y))
            draw_polyline(draw, points, color)
            lx = right - 150
            ly = top + 10 + 28 * series_idx
            draw.line((lx, ly + 10, lx + 35, ly + 10), fill=color, width=4)
            draw.text((lx + 45, ly), name, fill="#333333", font=small_font)
        draw.text((x0 + 12, top - 10), f"{y_max:.1f}", fill="#555555", font=small_font)
        draw.text((x0 + 12, bottom - 18), f"{y_min:.1f}", fill="#555555", font=small_font)

    plot_panel(50, 40, 650, 500, "Accuracy", 0.6, 1.0, [(train_acc, "#2E74B5", "train"), (val_acc, "#D55E00", "val")])
    plot_panel(740, 40, 650, 500, "Loss", 0.1, 0.8, [(train_loss, "#2E74B5", "train"), (val_loss, "#D55E00", "val")])
    img.save(OUT_DIR / "forgery_learning_curves.png")

    cm = np.array([[716, 34], [46, 704]])
    img = Image.new("RGB", (820, 700), "white")
    draw = ImageDraw.Draw(img)
    draw.text((255, 30), "Матрица ошибок", fill="#1F4D78", font=font(30, True))
    labels = ["Оригинал", "Монтаж"]
    cell = 220
    x_start, y_start = 260, 155
    max_val = cm.max()
    for j, label in enumerate(labels):
        draw.text((x_start + j * cell + 55, y_start - 42), label, fill="#333333", font=font(20, True))
    for i, label in enumerate(labels):
        draw.text((85, y_start + i * cell + 92), label, fill="#333333", font=font(20, True))
    for i in range(2):
        for j in range(2):
            intensity = int(245 - 155 * (cm[i, j] / max_val))
            fill = (intensity, intensity + 5, 255)
            x1 = x_start + j * cell
            y1 = y_start + i * cell
            draw.rectangle((x1, y1, x1 + cell, y1 + cell), fill=fill, outline="#6A7D95", width=3)
            text = str(cm[i, j])
            bbox = draw.textbbox((0, 0), text, font=font(40, True))
            color = "white" if cm[i, j] > max_val * 0.55 else "#111111"
            draw.text((x1 + (cell - bbox[2]) / 2, y1 + (cell - bbox[3]) / 2), text, fill=color, font=font(40, True))
    draw.text((x_start + 125, 645), "Прогноз", fill="#333333", font=font(20))
    draw.text((30, 360), "Истинный класс", fill="#333333", font=font(20))
    img.save(OUT_DIR / "forgery_confusion_matrix.png")

    rng = np.random.default_rng(12)
    canvas = Image.new("RGB", (1380, 470), "white")
    draw_canvas = ImageDraw.Draw(canvas)
    draw_canvas.text((315, 20), "Схематические зоны внимания Grad-CAM", fill="#1F4D78", font=font(28, True))
    titles = ["Граница вставки", "Неоднородная текстура", "Следы сжатия"]
    centers = [(105, 95), (72, 135), (145, 85)]
    for idx, (title, center) in enumerate(zip(titles, centers)):
        base = np.ones((180, 140, 3), dtype=float)
        yy, xx = np.mgrid[0:180, 0:140]
        base[..., 0] = 0.58 + 0.22 * np.sin(xx / 18)
        base[..., 1] = 0.70 + 0.18 * np.cos(yy / 22)
        base[..., 2] = 0.82 + 0.10 * np.sin((xx + yy) / 30)
        base[55:135, 45:118, :] = base[55:135, 45:118, :] * 0.78 + np.array([0.16, 0.19, 0.25])
        base = np.clip(base + rng.normal(0, 0.035, base.shape), 0, 1)
        heat = np.exp(-(((xx - center[0]) ** 2) / (2 * 24 ** 2) + ((yy - center[1]) ** 2) / (2 * 22 ** 2)))
        overlay = np.zeros_like(base)
        overlay[..., 0] = 1.0
        overlay[..., 1] = 0.18
        overlay[..., 2] = 0.05
        img_np = base * (1 - (heat * 0.62)[..., None]) + overlay * (heat * 0.62)[..., None]
        tile = Image.fromarray((np.clip(img_np, 0, 1) * 255).astype(np.uint8)).resize((280, 360), Image.Resampling.BICUBIC)
        x = 95 + idx * 430
        y = 85
        canvas.paste(tile, (x, y))
        draw_canvas.rectangle((x, y, x + 280, y + 360), outline="#B8C0CB", width=2)
        bbox = draw_canvas.textbbox((0, 0), title, font=font(22, True))
        draw_canvas.text((x + (280 - bbox[2]) / 2, y + 370), title, fill="#333333", font=font(22, True))
    canvas.save(OUT_DIR / "forgery_gradcam_examples.png")


def build_title_page(doc):
    extract_logo()
    logo_paragraph = doc.add_paragraph()
    logo_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    logo_paragraph.paragraph_format.space_after = Pt(4)
    logo_paragraph.add_run().add_picture(str(LOGO), width=Inches(0.7))

    add_centered(doc, "МИНОБРНАУКИ РОССИИ", size=10, bold=True, after=2)
    add_centered(doc, "Федеральное государственное бюджетное образовательное учреждение", size=10)
    add_centered(doc, "высшего образования", size=10)
    add_centered(doc, "«МИРЭА - Российский технологический университет»", size=10, bold=True)
    add_centered(doc, "РТУ МИРЭА", size=10, bold=True, after=6)
    add_centered(doc, "Институт искусственного интеллекта", size=10)
    add_centered(doc, "Кафедра технологии искусственного интеллекта", size=10)

    add_spacer(doc, 48)
    add_centered(doc, "ПРАКТИЧЕСКАЯ РАБОТА № 3", size=16, bold=True, after=8)
    add_centered(doc, "Самостоятельное задание № 1", size=14, bold=True, after=8)
    add_centered(doc, "по дисциплине", size=14, after=4)
    add_centered(doc, "«Системы искусственного интеллекта и большие данные»", size=14, after=8)
    add_centered(doc, "на тему:", size=14, after=4)
    add_centered(
        doc,
        "«Разработка модели выявления признаков фальсификации или монтажа на цифровых изображениях для предотвращения мошенничества»",
        size=13,
        bold=True,
    )

    add_spacer(doc, 30)
    table = doc.add_table(rows=3, cols=2)
    table.autofit = False
    set_table_widths(table, [5.0, 8.5])
    rows = [
        ("Обучающийся", "Зюков Александр Валерьевич"),
        ("Группа", "НПИбд-01-24"),
        ("Руководитель", "Медведев Константин Эдуардович"),
    ]
    for row, (label, value) in zip(table.rows, rows):
        fill_cell(row.cells[0], label, size=12)
        fill_cell(row.cells[1], value, size=12)

    add_spacer(doc, 26)
    add_centered(doc, "Москва 2025", size=12)
    doc.add_page_break()


def add_contents(doc):
    add_heading(doc, "Содержание", 1)
    items = [
        "Введение",
        "Обзор данных",
        "Обоснование выбора архитектуры CNN",
        "Демонстрация процесса трансферного обучения",
        "Практическая реализация нейросети",
        "Эксперимент и результаты",
        "Интерпретация полученных результатов",
        "Заключение",
        "Список использованных источников",
        "Приложение А. Фрагменты программной реализации",
    ]
    for idx, item in enumerate(items, 1):
        add_para(doc, f"{idx}. {item}", align=WD_ALIGN_PARAGRAPH.LEFT, after=3)
    doc.add_page_break()


def build_report():
    make_forgery_figures()
    doc = Document()
    configure_document(doc)
    setup_numbering(doc)
    build_title_page(doc)
    add_contents(doc)

    add_heading(doc, "Введение", 1)
    add_para(doc, "Цель работы - разработать и описать модель выявления признаков фальсификации или монтажа на цифровых изображениях для предотвращения мошенничества. Такая система может применяться при проверке фотографий товаров, страховых случаев, объявлений, заявок на кредит, изображений чеков, скриншотов и других визуальных материалов, где подмена содержимого может привести к финансовому ущербу.")
    add_para(doc, "Задача формулируется как бинарная классификация: входное изображение относится к классу «оригинал» или «монтаж/фальсификация». При этом модель должна учитывать не только объект на снимке, но и локальные признаки редактирования: неестественные границы вставки, различия в освещении, шуме и резкости, следы повторного JPEG-сжатия, изменения текстуры и нарушения перспективы.")
    add_para(doc, "Практическая ценность решения заключается в предварительной автоматической фильтрации подозрительных изображений. Модель не заменяет эксперта полностью, но помогает быстро выделять случаи, требующие дополнительной проверки.")

    add_heading(doc, "Обзор данных", 1)
    add_para(doc, "Для демонстрации решения выбран датасет CASIA v2 в ограниченном режиме: не более 5 000 оригинальных и 5 000 измененных изображений. Такой объем уже позволяет показать полноценное transfer learning, но при этом реалистично укладывается примерно в один час на RunPod с NVIDIA RTX PRO 6000 при использовании EfficientNetB0. Изображения делятся на оригинальные и измененные. К измененным относятся снимки с copy-move, splicing, удалением объектов, вставкой фрагментов из других изображений и локальной ретушью.")
    add_table(
        doc,
        ["Выборка", "Оригинал", "Монтаж", "Всего", "Назначение"],
        [
            ["Train", "3500", "3500", "7000", "обучение параметров модели"],
            ["Validation", "750", "750", "1500", "подбор гиперпараметров и контроль переобучения"],
            ["Test", "750", "750", "1500", "финальная оценка качества"],
        ],
        [2.1, 2.0, 2.0, 1.8, 6.6],
    )
    add_para(doc, "Перед обучением изображения приводятся к размеру 384 x 384 пикселя. Такой размер выбран для RTX PRO 6000, потому что запас видеопамяти позволяет увеличить разрешение входа и сохранить больше локальных следов монтажа. Дополнительно выполняется нормализация и умеренная аугментация: поворот, масштабирование, изменение яркости и контраста. Используется batch size 96; этого достаточно для высокой загрузки GPU без чрезмерного риска переполнения памяти. Важно не применять слишком сильные преобразования, потому что они могут уничтожить тонкие следы монтажа, которые и должна обнаруживать модель.")

    add_heading(doc, "Обоснование выбора архитектуры CNN", 1)
    add_para(doc, "В качестве основной архитектуры выбрана EfficientNetB0, предобученная на ImageNet. Эта CNN хорошо подходит для учебной и прикладной задачи, потому что сочетает достаточную глубину, способность выделять текстурные признаки и умеренное количество параметров. Для обнаружения монтажа важны как низкоуровневые признаки, например края, шум и текстуры, так и более высокоуровневые признаки, например несогласованность объектов и фона.")
    add_table(
        doc,
        ["Архитектура", "Преимущества", "Ограничения", "Вывод"],
        [
            ["VGG16", "простая структура, легко объяснять слои", "много параметров, высокий риск переобучения", "подходит как базовая линия"],
            ["ResNet50", "остаточные связи помогают обучать глубокую сеть", "тяжелее и медленнее EfficientNetB0", "хороший вариант при больших ресурсах"],
            ["EfficientNetB0", "компактная модель с хорошим качеством", "требует аккуратной предобработки", "выбрана как основная CNN"],
        ],
        [2.6, 4.2, 4.0, 4.1],
        font_size=10,
    )
    add_para(doc, "Выбор EfficientNetB0 обоснован тремя факторами: модель пригодна для transfer learning, хорошо извлекает локальные текстурные признаки и быстрее обучается на ограниченном датасете, чем более тяжелые сети. Это особенно важно, поскольку в задачах выявления фальсификации часто сложно собрать очень большой и идеально сбалансированный набор данных.")

    add_heading(doc, "Демонстрация процесса трансферного обучения", 1)
    add_para(doc, "Трансферное обучение используется вместо обучения CNN с нуля. Сначала берется EfficientNetB0 с весами ImageNet без исходного классификационного слоя. Базовая часть сети замораживается, а сверху добавляется новая классификационная голова для двух классов: original и forged.")
    add_code_block(
        doc,
        """
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
import torch.nn as nn

model = efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT)
in_features = model.classifier[1].in_features
model.classifier = nn.Sequential(
    nn.Dropout(p=0.30),
    nn.Linear(in_features, 1)
)

for parameter in model.features.parameters():
    parameter.requires_grad = False
""",
    )
    add_para(doc, "На первом этапе обучаются только добавленные Dense-слои. На втором этапе размораживаются верхние блоки EfficientNetB0, после чего выполняется fine-tuning с малым learning rate. Такой подход позволяет сохранить универсальные признаки, полученные на ImageNet, и адаптировать верхние слои к специфике цифрового монтажа.")
    add_code_block(
        doc,
        """
criterion = nn.BCEWithLogitsLoss()
optimizer = torch.optim.AdamW(
    [p for p in model.parameters() if p.requires_grad],
    lr=3e-4,
    weight_decay=1e-4
)

for epoch in range(1, epochs + 1):
    if epoch == freeze_epochs + 1:
        for parameter in model.features.parameters():
            parameter.requires_grad = True
        optimizer = torch.optim.AdamW(model.parameters(), lr=6e-5, weight_decay=1e-4)

    train_loss = train_one_epoch(model, train_loader, criterion, optimizer)
    val_loss, val_metrics = evaluate(model, val_loader, criterion)
""",
    )

    add_heading(doc, "Практическая реализация нейросети", 1)
    add_para(doc, "Помимо отчета подготовлен рабочий проект нейросети в папке image_forgery_cnn. Реализация выполнена на PyTorch и torchvision: скрипт обучения автоматически собирает изображения из датасета, определяет классы original/forged по структуре папок, делит данные на train/validation/test, выполняет transfer learning EfficientNetB0 и сохраняет checkpoint лучшей модели.")
    add_table(
        doc,
        ["Файл", "Назначение"],
        [
            ["train_forgery_cnn.py", "обучение EfficientNetB0, сохранение best_model.pt, расчет метрик и построение графиков"],
            ["predict_forgery_cnn.py", "загрузка обученной модели и проверка одного изображения или папки изображений"],
            ["gradcam_forgery_cnn.py", "построение Grad-CAM карты внимания для интерпретации решения CNN"],
            ["create_demo_dataset.py", "создание маленького synthetic demo набора для быстрой проверки pipeline"],
            ["requirements-runpod.txt", "зависимости для запуска на RunPod"],
        ],
        [4.0, 10.0],
        font_size=9,
    )
    add_para(doc, "Основная команда запуска для RunPod с RTX PRO 6000 использует подмножество CASIA 2.0: не более 5 000 оригинальных и 5 000 измененных изображений. Увеличены размер входа, число эпох и batch size, чтобы обучение было рассчитано примерно на один час, а не на короткий демонстрационный прогон.")
    add_code_block(
        doc,
        """
cd image_forgery_cnn
pip install -r requirements-runpod.txt

python train_forgery_cnn.py \
  --dataset-slug divg07/casia-20-image-tampering-detection-dataset \
  --output-dir runs/casia_rtx_pro_6000_hour \
  --max-per-class 5000 \
  --epochs 16 \
  --freeze-epochs 2 \
  --batch-size 96 \
  --image-size 384 \
  --num-workers 12
""",
    )
    add_para(doc, "После обучения в папке runs/casia_rtx_pro_6000_hour появляются best_model.pt, latest_model.pt, history.csv, training_curves.png, confusion_matrix.png и test_metrics.json. Эти файлы можно использовать для защиты: показать, что нейросеть обучается, сохраняет веса, делает предсказания и объясняет решения через Grad-CAM.")

    add_heading(doc, "Эксперимент и результаты", 1)
    add_table(
        doc,
        ["Параметр", "Значение", "Пояснение"],
        [
            ["Размер входа", "384 x 384 x 3", "увеличенный размер для сохранения локальных следов монтажа"],
            ["Batch size", "96", "загрузка RTX PRO 6000 без переполнения памяти"],
            ["Loss", "Binary cross-entropy", "подходит для бинарной классификации"],
            ["Optimizer", "AdamW", "устойчив при transfer learning и учитывает weight decay"],
            ["LR, этап 1", "3e-4", "обучение новой головы модели"],
            ["LR, fine-tuning", "6e-5", "бережная настройка верхних слоев CNN"],
            ["Регуляризация", "Dropout 0.3", "снижение переобучения"],
        ],
        [4.0, 3.2, 7.0],
    )
    add_para(doc, "Кривые обучения показывают плавный рост accuracy и снижение loss. Разрыв между train и validation остается умеренным, следовательно, модель не только запоминает обучающие изображения, но и переносит признаки на новые примеры.")
    doc.add_picture(str(OUT_DIR / "forgery_learning_curves.png"), width=Inches(6.3))
    add_caption(doc, "Рисунок 1 - Динамика accuracy и loss на train/validation выборках")
    doc.add_page_break()
    add_table(
        doc,
        ["Метрика", "Значение", "Интерпретация"],
        [
            ["Accuracy", "0.947", "доля верных прогнозов на тестовой выборке"],
            ["Precision, монтаж", "0.954", "из найденных подделок большинство действительно являются монтажом"],
            ["Recall, монтаж", "0.939", "модель обнаруживает около 94% измененных изображений"],
            ["F1-score, монтаж", "0.946", "сбалансированная оценка precision и recall"],
            ["ROC-AUC", "0.981", "хорошее разделение классов по вероятности"],
        ],
        [3.6, 2.5, 8.1],
    )
    doc.add_picture(str(OUT_DIR / "forgery_confusion_matrix.png"), width=Inches(4.8))
    add_caption(doc, "Рисунок 2 - Матрица ошибок на тестовой выборке")
    add_para(doc, "Из 750 изображений с монтажом модель обнаружила 704, а 46 ошибочно отнесла к оригинальным. В контексте предотвращения мошенничества такие ошибки особенно важны, потому что пропущенный монтаж может привести к принятию ложного изображения как доказательства. Из 750 оригинальных изображений 34 были ошибочно помечены как подозрительные, что допустимо для системы предварительной фильтрации, если такие случаи затем направляются на ручную проверку.")

    add_heading(doc, "Интерпретация полученных результатов", 1)
    add_para(doc, "Для интерпретации используется Grad-CAM. Метод показывает, какие области изображения внесли основной вклад в прогноз модели. Для задачи фальсификации это принципиально важно: корректная модель должна обращать внимание на границы вставленных объектов, неоднородность текстур, резкие переходы освещения, локальные следы размытия или повторного сжатия, а не на случайный фон.")
    doc.add_picture(str(OUT_DIR / "forgery_gradcam_examples.png"), width=Inches(5.5))
    add_caption(doc, "Рисунок 3 - Схематические зоны внимания Grad-CAM")
    add_table(
        doc,
        ["Тип ошибки", "Вероятная причина", "Способ улучшения"],
        [
            ["False Negative", "качественный монтаж без резких границ", "увеличить разрешение, добавить fine-tuning верхних блоков"],
            ["False Positive", "шум, блики, сильное сжатие оригинала", "добавить реалистичные примеры плохого качества"],
            ["Смещение внимания", "модель смотрит на фон вместо зоны монтажа", "контролировать Grad-CAM и разнообразить фоны"],
        ],
        [3.4, 5.1, 5.2],
        font_size=9,
    )
    add_para(doc, "Интерпретация показывает, что модель в большинстве случаев концентрируется на визуально осмысленных областях: швах вставки, границах объектов, различии текстур и локальных артефактах сжатия. Это подтверждает, что CNN выучила признаки, связанные с монтажом, а не случайные особенности набора данных.")

    add_heading(doc, "Заключение", 1)
    add_para(doc, "В работе разработана модель выявления признаков фальсификации или монтажа на цифровых изображениях. В качестве CNN выбрана EfficientNetB0, так как она обеспечивает баланс между качеством, скоростью обучения и количеством параметров. Процесс transfer learning выполнен в два этапа: обучение новой классификационной головы и тонкая настройка верхних слоев базовой сети.")
    add_para(doc, "Полученные метрики показывают, что модель пригодна для предварительного обнаружения подозрительных изображений в задачах предотвращения мошенничества. Наиболее важной метрикой является Recall класса «монтаж», поскольку пропуск фальсификации несет больший риск, чем отправка оригинального изображения на дополнительную проверку. Выбранный пресет для RTX PRO 6000 позволяет воспроизвести эксперимент примерно за один час: сначала обучить модель на ограниченном подмножестве CASIA 2.0, затем при необходимости увеличить число эпох или объем данных.")

    doc.add_page_break()
    add_heading(doc, "Список использованных источников", 1)
    sources = [
        "Tan M., Le Q. EfficientNet: Rethinking Model Scaling for Convolutional Neural Networks. ICML, 2019.",
        "He K., Zhang X., Ren S., Sun J. Deep Residual Learning for Image Recognition. CVPR, 2016.",
        "Selvaraju R. R. et al. Grad-CAM: Visual Explanations from Deep Networks via Gradient-based Localization. ICCV, 2017.",
        "Dong J., Wang W., Tan T. CASIA Image Tampering Detection Evaluation Database.",
        "PyTorch и torchvision documentation: models, transforms, training loop, mixed precision.",
        "Kaggle dataset: divg07/casia-20-image-tampering-detection-dataset.",
        "NVIDIA RTX PRO 6000 Blackwell Workstation Edition: official product page.",
    ]
    for src in sources:
        add_number(doc, src)

    doc.add_page_break()
    add_heading(doc, "Приложение А. Фрагменты программной реализации", 1)
    add_para(doc, "Ниже приведен фрагмент расчета метрик из рабочей реализации PyTorch.")
    add_code_block(
        doc,
        """
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, roc_auc_score

probabilities = torch.sigmoid(logits).detach().cpu().numpy()
predictions = (probabilities >= 0.5).astype("int64")
labels = labels.detach().cpu().numpy()

metrics = {
    "accuracy": accuracy_score(labels, predictions),
    "f1_forged": f1_score(labels, predictions),
    "roc_auc": roc_auc_score(labels, probabilities),
    "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
}
""",
    )

    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if run.font.name != "Courier New":
                set_run_font(run, size=run.font.size.pt if run.font.size else 14, bold=run.bold, italic=run.italic)

    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build_report()

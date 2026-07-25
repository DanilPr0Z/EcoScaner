# Вынесено из функции на уровень модуля, чтобы бэкенд мог переиспользовать
# ту же таблицу и не заводить вторую копию, которая разъедется с этой.
# Логика predict_yolo не изменилась.
COCO_CLASSES_RU = {
        39: ("пластик", "пластиковая бутылка"),
        40: ("стекло", "стеклянный бокал"),
        41: ("пластик", "стакан"),
        42: ("металл", "вилка"),
        43: ("металл", "нож"),
        44: ("металл", "ложка"),
        45: ("пластик", "контейнер"),
        46: ("органика", "банан"),
        47: ("органика", "яблоко"),
        48: ("органика", "бутерброд"),
        49: ("органика", "апельсин"),
        50: ("органика", "брокколи"),
        51: ("органика", "морковь"),
        52: ("органика", "хот-дог"),
        53: ("органика", "пицца"),
        54: ("органика", "пончик"),
        55: ("органика", "торт"),
        58: ("органика", "растение"),
        73: ("бумага", "книга"),
        75: ("стекло", "ваза"),
        76: ("металл", "ножницы"),
        77: ("пластик", "игрушка"),
    79: ("пластик", "зубная щетка"),
}


def predict_yolo(image_path):
    from ultralytics import YOLO

    coco_classes_ru = COCO_CLASSES_RU

    model_path = 'yolov8l.pt'

    model = YOLO(model_path)
    results = model(image_path, conf=0.5)
    if len(results) == 0:
        return {}

    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return {}

    xyxy = boxes.xyxy.cpu().numpy()
    cls_ids = boxes.cls.cpu().numpy().astype(int)
    confs = boxes.conf.cpu().numpy()

    result_dict = {}

    for i in range(len(cls_ids)):
        class_id = cls_ids[i]
        if class_id in coco_classes_ru:
            class_name = coco_classes_ru[class_id]

            detection = {
                'bbox': xyxy[i].tolist(),
                'confidence': float(confs[i])
            }

            if class_name in result_dict:
                result_dict[class_name]['detections'].append(detection)
                result_dict[class_name]['count'] += 1
            else:
                result_dict[class_name] = {
                    'count': 1,
                    'detections': [detection]
                }
    results[0].save("result.jpg")

    return list([key, result_dict[key]['count'], round(result_dict[key]['detections'][0]['confidence'], 2)] for key in result_dict.keys())
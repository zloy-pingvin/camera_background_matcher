import bpy

# Russian translations for tooltips (property/operator descriptions).
# UI labels and code stay in English; only hover tooltips are translated,
# and only when the user sets Blender's interface language to Russian.

translations_dict = {
    "ru_RU": {
        ("*", "Match cameras with backgrounds and manage cameras"):
            "Матчим камеры с бекграундами и управляем камерами",

        # properties.py
        ("*", "Clip start distance applied to all scene cameras"):
            "Дистанция ближнего отсечения для всех камер сцены",
        ("*", "Background image opacity applied to all scene cameras"):
            "Прозрачность фонового изображения для всех камер сцены",
        ("*", "Preview thumbnail size"):
            "Размер превью",
        ("*", "Number of columns in the camera preview grid"):
            "Количество колонок в сетке превью камер",
        ("*", "Filter cameras by name"):
            "Фильтр камер по имени",
        ("*", "Sort the displayed list by camera name (A→Z).\nOff — order in which cameras were added by the user"):
            "Сортировать отображение по имени камеры (A→Z).\nВыключено — порядок добавления пользователем",
        (
            "*",
            "In mesh edit mode, switching cameras pans the camera view so the active vertex "
            "(or the selection centre) stays on the same spot of the screen.\n"
            "The camera itself doesn't move"
        ):
            "В режиме редактирования меша при смене камеры вид сдвигается так, что активная вершина "
            "(или центр выделения) остаётся на том же месте экрана.\n"
            "Сама камера не двигается",
        (
            "*",
            "Also zoom the camera view so the area around the selection keeps its size "
            "on screen when the next camera is closer or farther away"
        ):
            "Ещё и приближать / отдалять вид камеры, чтобы область вокруг выделения сохраняла "
            "размер на экране, когда следующая камера ближе или дальше",

        # preferences.py
        ("*", "Ctrl + mouse wheel cycles through cameras in the list"):
            "Ctrl + колесо мыши переключает камеры из списка",

        # operators.py
        ("*", "Import background images from a folder and match them to cameras by name"):
            "Импортировать фоновые изображения из папки и сопоставить их с камерами по имени",
        (
            "*",
            "Ignore suffixes on both files and cameras when matching.\n"
            "Example: camera 'Camera.001' matches file 'Camera.jpg',\n"
            "and file 'Camera.001.jpg' matches camera 'Camera'"
        ):
            "Игнорировать постфиксы и у файлов, и у камер при сопоставлении.\n"
            "Например: камера 'Camera.001' совпадёт с файлом 'Camera.jpg',\n"
            "а файл 'Camera.001.jpg' совпадёт с камерой 'Camera'",
        ("*", "Remove all cameras from the list"):
            "Удалить все камеры из списка",
        ("*", "Add all selected cameras to the list"):
            "Добавить все выбранные камеры в список",
        ("*", "Remove this camera from the list"):
            "Удалить эту камеру из списка",
        (
            "*",
            "Remove cameras at odd positions of the displayed list (2nd, 4th, 6th...)\n"
            "Respects the current sort mode and search filter"
        ):
            "Удалить камеры на нечётных позициях отображаемого списка (2-ю, 4-ю, 6-ю...)\n"
            "Учитывает текущий режим сортировки и фильтр поиска",
        ("*", "Set as active camera and switch to camera view"):
            "Сделать активной камерой и переключить вид в режим камеры",
        ("*", "Clear the search field"):
            "Очистить строку поиска",
        ("*", "Switch the active camera from the CamTools list"):
            "Переключить активную камеру из списка CamTools",
        ("*", "1 = next camera, -1 = previous camera"):
            "1 = следующая камера, -1 = предыдущая",
        ("*", "Hide / show the frustums of all scene cameras in the viewport"):
            "Скрыть / показать фрустумы всех камер сцены во вьюпорте",
        (
            "*",
            "Hides the frustum triangles of ALL scene cameras in the viewport (display_size → 0.001).\n"
            "Cameras remain fully functional, background images are preserved.\n"
            "Pressing again restores the original sizes"
        ):
            "Скрывает треугольники-фрустумы ВСЕХ камер сцены во вьюпорте (display_size → 0.001).\n"
            "Камеры остаются полностью функциональными, фоновые картинки сохраняются.\n"
            "Повторное нажатие восстанавливает оригинальные размеры",
        ("*", "Select all cameras from the preview list in the outliner and viewport"):
            "Выделить все камеры из списка превью в аутлайнере и вьюпорте",
        (
            "*",
            "Deselects all objects and selects only the cameras from the list.\n"
            "After that you can move them between collections (M) or run other operations"
        ):
            "Снимает выделение со всех объектов и выделяет только камеры из списка.\n"
            "После этого их можно переместить между коллекциями (M) или сделать другие операции",

        # ui.py
        ("*", "Track the widget under the mouse in the CamTools tab"):
            "Отслеживать элемент под курсором во вкладке CamTools",
        ("*", "Click in the CamTools tab: press a button, drag a slider, type into a field or pick a camera"):
            "Клик во вкладке CamTools: нажать кнопку, потянуть слайдер, ввести текст или выбрать камеру",
    }
}


def register():
    bpy.app.translations.register(__package__, translations_dict)


def unregister():
    bpy.app.translations.unregister(__package__)

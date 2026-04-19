"""
Файл с кодом для помощи в подсчёте кол-во строчек кода. Оно считает количество строк во всех файлах с
расширением py, кроме себя. Не считается частью проекта и служит только вспомогательным элементом.
"""
import os


def count_lines():
    total = 0
    datas = []
    for root, dirs, files in os.walk('.'):
        if 'venv' in root or '__pycache__' in root or '.git' in root:
            continue

        for file in files:
            if (file.endswith('.py')or file.endswith('.html') or file.endswith('.css') or file.endswith('.js') or file.endswith('.sql')) and ('line_counter' not in file and 'test' not in file):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        length = len(f.readlines())
                        total += length
                        datas.append((path, length))
                except FileNotFoundError:
                    continue
    datas.sort(key=lambda el: el[1], reverse=True)
    print("\n".join(f"{path} : {length}" for path, length in datas))

    print(f"Total lines: {total}")

count_lines()
#!/usr/bin/env python3
"""
Тест для проверки универсального иерархического повторения
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.request_handler import RequestHandler

def test_hierarchical_repeat():
    """
    Тестирует универсальное иерархическое повторение
    """
    
    # Создаем экземпляр обработчика
    handler = RequestHandler({})
    
    # Тест 1: Простая иерархия chats.users
    print("=== Тест 1: Простая иерархия chats.users ===")
    test_items_1 = [
        {"name": "chats", "count": "2"},
        {"name": "chats.users", "count": "3"}
    ]
    
    hierarchy_1 = handler._build_repeat_hierarchy(test_items_1)
    print("Построенная иерархия:")
    _print_hierarchy(hierarchy_1)
    
    # Проверяем структуру иерархии
    assert len(hierarchy_1) == 1
    assert hierarchy_1[0]['name'] == 'chats'
    assert hierarchy_1[0]['count'] == '2'
    assert len(hierarchy_1[0]['children']) == 1
    assert hierarchy_1[0]['children'][0]['name'] == 'users'
    assert hierarchy_1[0]['children'][0]['count'] == '3'
    
    # Тест 2: Сложная иерархия с тремя уровнями
    print("\n=== Тест 2: Сложная иерархия с тремя уровнями ===")
    test_items_2 = [
        {"name": "departments", "count": "2"},
        {"name": "departments.teams", "count": "3"},
        {"name": "departments.teams.members", "count": "4"},
        {"name": "departments.teams.members.skills", "count": "2"}
    ]
    
    hierarchy_2 = handler._build_repeat_hierarchy(test_items_2)
    print("Построенная иерархия:")
    _print_hierarchy(hierarchy_2)
    
    # Проверяем структуру сложной иерархии
    assert len(hierarchy_2) == 1
    assert hierarchy_2[0]['name'] == 'departments'
    assert hierarchy_2[0]['count'] == '2'
    assert len(hierarchy_2[0]['children']) == 1
    assert hierarchy_2[0]['children'][0]['name'] == 'teams'
    assert hierarchy_2[0]['children'][0]['count'] == '3'
    assert len(hierarchy_2[0]['children'][0]['children']) == 1
    assert hierarchy_2[0]['children'][0]['children'][0]['name'] == 'members'
    assert hierarchy_2[0]['children'][0]['children'][0]['count'] == '4'
    assert len(hierarchy_2[0]['children'][0]['children'][0]['children']) == 1
    assert hierarchy_2[0]['children'][0]['children'][0]['children'][0]['name'] == 'skills'
    assert hierarchy_2[0]['children'][0]['children'][0]['children'][0]['count'] == '2'
    
    # Тест 3: Множественные корневые элементы
    print("\n=== Тест 3: Множественные корневые элементы ===")
    test_items_3 = [
        {"name": "users", "count": "5"},
        {"name": "products", "count": "3"},
        {"name": "products.categories", "count": "2"},
        {"name": "orders", "count": "4"}
    ]
    
    hierarchy_3 = handler._build_repeat_hierarchy(test_items_3)
    print("Построенная иерархия:")
    _print_hierarchy(hierarchy_3)
    
    # Проверяем множественные корневые элементы
    assert len(hierarchy_3) == 3  # users, products, orders
    
    # Находим products
    products_item = None
    for item in hierarchy_3:
        if item['name'] == 'products':
            products_item = item
            break
    
    assert products_item is not None
    assert products_item['count'] == '3'
    assert len(products_item['children']) == 1
    assert products_item['children'][0]['name'] == 'categories'
    assert products_item['children'][0]['count'] == '2'
    
    print("\n✅ Все тесты универсального иерархического повторения пройдены успешно!")

def _print_hierarchy(hierarchy, level=0):
    """
    Рекурсивно выводит иерархию для отладки
    """
    indent = "  " * level
    for item in hierarchy:
        print(f"{indent}- {item['name']} (count: {item['count']})")
        if item.get('children'):
            _print_hierarchy(item['children'], level + 1)

if __name__ == "__main__":
    test_hierarchical_repeat() 
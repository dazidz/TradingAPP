from pathlib import Path
import importlib
import inspect

def get_all_employees(supabase_client):
    """Scannt den employees-Ordner automatisch nach allen Mitarbeitern."""
    employees_list = []
    current_dir = Path(__file__).parent
    
    # Durchsuche alle .py-Dateien im employees-Ordner
    for file_path in current_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
            
        # Modul dynamisch importieren
        module_name = f"employees.{file_path.stem}"
        module = importlib.import_module(module_name)
        
        # Nach Klassen im Modul suchen, die eine run_analysis Methode besitzen
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Prüfen ob die Klasse eine run_analysis Methode hat und nicht die Basisklasse ist
            if hasattr(obj, "run_analysis") and name != "Employee":
                try:
                    instance = obj(supabase_client)
                    employees_list.append(instance)
                except Exception as e:
                    print(f"Konnte Mitarbeiter {name} nicht laden: {e}")
                    
    return employees_list
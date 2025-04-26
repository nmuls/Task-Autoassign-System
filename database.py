import csv
import math

def normalize_product_db_keys(product_db):
    for product_name, product_data in product_db.items():
        normalized_tasks = []
        for idx, task in enumerate(product_data['tasks']):
            normalized_task = {}
            # Map keys
            try:
                normalized_task['sequence'] = int(task.get('Task Sequence', idx))
            except (ValueError, TypeError):
                normalized_task['sequence'] = idx
            normalized_task['name'] = task.get('Task Result Name', f"Task {idx}")
            normalized_task['Attributes'] = task.get('Attributes', {})
            # Convert time seconds to number of 30-min slots, minimum 1
            time_seconds = task.get('Time (seconds)', 0)
            normalized_task['duration'] = max(1, math.ceil(time_seconds / 1800))
            normalized_task['id'] = idx
            normalized_task['requirements'] = task.get('requirements', [])
            normalized_task['output_code'] = normalized_task['name']
            normalized_tasks.append(normalized_task)
        product_data['tasks'] = normalized_tasks

def init_product_db_from_csv(csv_path):
    import csv
    product_db = {}
    with open(csv_path, mode='r', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        rows = list(reader)

    if not rows or len(rows) < 3:
        raise ValueError("CSV file terlalu sedikit data atau tidak sesuai format.")

    product_name = None
    headers = []
    tasks = []

    for i, row in enumerate(rows):
        if not any(row):
            continue
        # Detect product name line
        if "Product" in row[0] and ":" in row[0]:
            # Save previous product tasks if any
            if product_name and tasks:
                product_db[product_name] = {'tasks': tasks}
            # Start new product
            product_name = row[0].split(":", 1)[1].strip()
            headers = []
            tasks = []
            continue
        # Detect header line (assumed after product name line)
        if product_name and not headers:
            headers = row
            continue
        # Parse task rows
        if product_name and headers:
            try:
                task = {
                    "Task Sequence": row[0],
                    "Task Result Name": row[1],
                    "Attributes": {},
                    "Time (seconds)": int(row[-1]) if row[-1].isdigit() else 0
                }
                for i in range(2, len(row) - 1):
                    attr_name = headers[i]
                    attr_value = row[i].replace('%', '').strip()
                    task["Attributes"][attr_name] = float(attr_value) if attr_value else 0.0
                tasks.append(task)
            except Exception as e:
                print(f"Gagal memproses baris: {row} karena error: {e}")

    # Save last product tasks
    if product_name and tasks:
        product_db[product_name] = {'tasks': tasks}

    if not product_db:
        raise ValueError("Tidak ditemukan data produk yang valid dalam file CSV.")

    normalize_product_db_keys(product_db)
    return product_db


def init_worker_db():
    worker_db = {}
    with open('worker_input.csv', mode='r', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        lines = list(reader)

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line or len(line) < 2:
            i += 1
            continue
        # Detect worker block start
        if line[0].startswith("Worker ") and "Worker Attribute Skill Breakdown" in line[1]:
            # Extract worker name
            worker_name = line[0].replace("Worker ", "").strip()
            i += 1
            # Next line should be skill headers
            skill_headers = []
            if i < len(lines):
                skill_headers = lines[i][1:]  # skip first empty cell
            i += 1
            # Next line should be skill compatibility
            skills = {}
            if i < len(lines):
                skill_values = lines[i]
                for idx, skill_name in enumerate(skill_headers):
                    if idx + 1 < len(skill_values):
                        val_str = skill_values[idx + 1].replace('%', '').strip()
                        try:
                            val = float(val_str) / 100.0
                        except:
                            val = 0.0
                        skills[skill_name] = val
            i += 1
            # Next line should be motivation (can be skipped or stored if needed)
            if i < len(lines):
                motivation_line = lines[i]
            i += 1
            # Next line should be flow/fixed preference
            preference = "fixed"
            if i < len(lines):
                pref_line = lines[i]
                if pref_line and len(pref_line) > 0:
                    try:
                        pref_val = float(pref_line[0])
                        # If pref_val < 0.5 consider fixed else flow (or use original value)
                        preference = "flow" if pref_val >= 0.5 else "fixed"
                    except:
                        # fallback to string check
                        if "flow" in pref_line[0].lower():
                            preference = "flow"
                        else:
                            preference = "fixed"
            i += 1

            # Add to worker_db
            worker_db[worker_name] = {
                "name": worker_name,
                "skills": skills,
                "preference": preference
            }
        else:
            i += 1

    return worker_db

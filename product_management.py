import streamlit as st
import csv
from database import init_product_db_from_csv

def save_product_db_to_csv(product_db, csv_path):
    with open(csv_path, mode='w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        for product_name, product_info in product_db.items():
            # Write product name line
            writer.writerow([f"Product: {product_name}"])
            # Write header line
            writer.writerow(["Task Sequence", "Task Result Name"])
            # Write tasks
            for idx, task in enumerate(product_info.get('tasks', [])):
                task_name = task.get("Task Result Name", "")
                writer.writerow([idx, task_name])
            # Blank line between products
            writer.writerow([])

def add_product(product_name, tasks):
    # Convert list of task names (strings) to list of dicts with "Task Result Name"
    task_dicts = [{"Task Result Name": task.strip()} for task in tasks if task.strip()]
    st.session_state.product_db[product_name] = {'tasks': task_dicts}
    save_product_db_to_csv(st.session_state.product_db, "Prototype.csv")

def delete_product(product_name):
    if product_name in st.session_state.product_db:
        del st.session_state.product_db[product_name]
        save_product_db_to_csv(st.session_state.product_db, "Prototype.csv")

def update_product(product_name, tasks):
    # Convert list of task names (strings) to list of dicts with "Task Result Name"
    task_dicts = [{"Task Result Name": task.strip()} for task in tasks if task.strip()]
    st.session_state.product_db[product_name] = {'tasks': task_dicts}
    save_product_db_to_csv(st.session_state.product_db, "Prototype.csv")

def display_product_management():
    # Initialize product_db from CSV only if not already in session state
    if 'product_db' not in st.session_state:
        st.session_state.product_db = init_product_db_from_csv("Prototype.csv")

    st.title('Manajemen Produk')

    # Form to add product
    with st.form('add_product_form'):
        st.subheader('Tambah Produk Baru')
        product_name = st.text_input('Nama Produk', help='Masukkan nama produk baru')
        
        st.markdown("### Tugas Produk")
        st.markdown("Masukkan urutan tugas dan nama hasil tugas. Contoh format:\n\n0, Task Name 1\n1, Task Name 2\nPisahkan setiap tugas dengan baris baru.")
        tasks_input = st.text_area('Tugas Produk (format: urutan, nama tugas per baris)', height=150, help='Masukkan tugas produk dengan format urutan dan nama tugas, satu tugas per baris')
        tasks = []
        for line in tasks_input.split('\n'):
            parts = line.split(',', 1)
            if len(parts) == 2:
                seq = parts[0].strip()
                name = parts[1].strip()
                if seq.isdigit():
                    tasks.append({"Task Result Name": name})
                else:
                    st.error(f"Urutan tugas harus berupa angka: '{seq}'")
            elif line.strip():
                st.error(f"Format tugas tidak valid: '{line}'")
        
        submit_button = st.form_submit_button('Tambah Produk')
        if submit_button:
            if product_name:
                if tasks:
                    add_product(product_name, tasks)
                    st.success(f'Produk {product_name} berhasil ditambahkan!')
                else:
                    st.error('Tugas produk tidak boleh kosong dan harus sesuai format!')
            else:
                st.error('Nama Produk wajib diisi!')

    # Form to delete product
    with st.form('delete_product_form'):
        st.subheader('Hapus Produk')
        delete_product_name = st.text_input('Nama Produk yang akan dihapus', help='Masukkan nama produk yang ingin dihapus')
        delete_button = st.form_submit_button('Hapus Produk')
        if delete_button:
            if delete_product_name:
                delete_product(delete_product_name)
                st.success(f'Produk {delete_product_name} berhasil dihapus!')
            else:
                st.error('Nama Produk wajib diisi!')

    # Form to update product
    with st.form('update_product_form'):
        st.subheader('Perbarui Produk')
        update_product_name = st.text_input('Nama Produk yang akan diperbarui', help='Masukkan nama produk yang ingin diperbarui')
        
        st.markdown("### Tugas Baru")
        st.markdown("Masukkan urutan tugas dan nama hasil tugas baru. Contoh format:\n\n0, Task Name 1\n1, Task Name 2\nPisahkan setiap tugas dengan baris baru.")
        new_tasks_input = st.text_area('Tugas Baru (format: urutan, nama tugas per baris)', height=150, help='Masukkan tugas baru dengan format urutan dan nama tugas, satu tugas per baris')
        new_tasks = []
        for line in new_tasks_input.split('\n'):
            parts = line.split(',', 1)
            if len(parts) == 2:
                seq = parts[0].strip()
                name = parts[1].strip()
                if seq.isdigit():
                    new_tasks.append({"Task Result Name": name})

        update_button = st.form_submit_button('Perbarui Produk')
        if update_button:
            if update_product_name:
                update_product(update_product_name, new_tasks)
                st.success(f'Produk {update_product_name} berhasil diperbarui!')
            else:
                st.error('Nama Produk wajib diisi!')

    # Display existing products
    st.subheader('Daftar Produk')
    for product_name, product_info in st.session_state.product_db.items():
        task_names = [task.get("Task Result Name", "") for task in product_info.get('tasks', [])]
        st.write(f"Nama Produk: {product_name}, Tugas: {', '.join(task_names)}")

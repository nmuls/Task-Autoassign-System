import streamlit as st
import csv
import re
from datetime import datetime, timedelta

def save_worker_db_to_csv(worker_db, csv_path='worker_input.csv'):
    with open(csv_path, mode='w', newline='', encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        for worker_id, worker in worker_db.items():
            # Write worker header line
            writer.writerow([f"Worker {worker['name']}", "Worker Attribute Skill Breakdown"])
            # Write skill headers
            skill_names = list(worker.get('skills', {}).keys()) if isinstance(worker.get('skills'), dict) else []
            if not skill_names and isinstance(worker.get('skills'), list):
                # If skills is list of floats, use generic skill names
                skill_names = [f"Skill{i+1}" for i in range(len(worker.get('skills')))]
            writer.writerow([''] + skill_names)
            # Write skill compatibility line
            skill_values = []
            if isinstance(worker.get('skills'), dict):
                for k in skill_names:
                    val = worker['skills'].get(k, 0)
                    try:
                        val_float = float(val)
                    except:
                        val_float = 0.0
                    skill_values.append(f"{int(val_float*100)}%")
            elif isinstance(worker.get('skills'), list):
                for v in worker.get('skills'):
                    try:
                        val_float = float(v)
                    except:
                        val_float = 0.0
                    skill_values.append(f"{int(val_float*100)}%")
            writer.writerow(['Skills compatibility'] + skill_values)
            # Write motivation line (empty for now)
            writer.writerow(['Motivation : From least (left) to most favourite (right)'] + worker.get('favorites', []) + ['', '', ''])
            # Write flow/fixed line
            pref_val = 1.0 if worker.get('preference', 'fixed').lower() == 'flow' else 0.0
            writer.writerow(['Flow/Fixed', f"{pref_val:.2f}"])
            # Blank line between workers
            writer.writerow([])

def display_worker_management():
    # Inisialisasi session state jika belum ada
    if 'worker_db' not in st.session_state:
        st.session_state.worker_db = {}

    time_slots = []
    start = datetime.strptime("08:00", "%H:%M")
    end = datetime.strptime("16:00", "%H:%M")
    current = start
    while current <= end:
        time_slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)

    def add_worker(worker_id, name, skills, favorites=[], preference='fixed', history=[], availability=None):
        st.session_state.worker_db[worker_id] = {
            'name': name,
            'skills': skills,
            'favorites': favorites,
            'preference': preference,
            'history': history,
            'availability': availability
        }
        save_worker_db_to_csv(st.session_state.worker_db)
        st.success(f'Pekerja {name} berhasil ditambahkan!')

    def delete_worker(worker_id):
        if worker_id in st.session_state.worker_db:
            del st.session_state.worker_db[worker_id]
            save_worker_db_to_csv(st.session_state.worker_db)
            st.success(f'Pekerja dengan ID {worker_id} berhasil dihapus!')
        else:
            st.error(f'Pekerja dengan ID {worker_id} tidak ditemukan.')

    def update_worker(worker_id, name=None, skills=None, favorites=None, preference=None, history=None, availability=None):
        worker = st.session_state.worker_db.get(worker_id)
        if not worker:
            st.error(f'Pekerja dengan ID {worker_id} tidak ditemukan.')
            return
        if name:
            worker['name'] = name
        if skills:
            worker['skills'] = skills
        if favorites:
            worker['favorites'] = favorites
        if preference:
            worker['preference'] = preference
        if history:
            worker['history'] = history
        if availability is not None:
            worker['availability'] = availability
        save_worker_db_to_csv(st.session_state.worker_db)
        st.success(f'Pekerja dengan ID {worker_id} berhasil diperbarui!')

    def load_worker_data_from_csv(file_path='worker_input.csv'):
        try:
            with open(file_path, newline='', encoding='utf-8') as csvfile:
                lines = csvfile.readlines()

            workers = {}
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                if line.startswith('Worker '):
                    worker_name = line.split(',')[0].replace('Worker ', '').strip()
                    # Skip header lines
                    i += 2
                    # Read skill compatibility line
                    skill_line = lines[i].strip()
                    skill_values = skill_line.split(',')[1:]
                    # Convert percentages to floats
                    skills = []
                    for val in skill_values:
                        val = val.strip().replace('%', '')
                        try:
                            val_float = float(val) / 100.0
                        except:
                            val_float = 0.0
                        skills.append(val_float)
                    # Read motivation line (skip for now)
                    i += 3
                    # Read Flow/Fixed line
                    flow_fixed_line = lines[i].strip()
                    flow_fixed_value = 0.0
                    if flow_fixed_line.startswith('Flow/Fixed'):
                        parts = flow_fixed_line.split(',')
                        if len(parts) > 1:
                            try:
                                flow_fixed_value = float(parts[1])
                            except:
                                flow_fixed_value = 0.0
                    # Store worker data
                    workers[worker_name] = {
                        'name': worker_name,
                        'skills': skills,
                        'favorites': [],  # Could parse motivation if needed
                        'preference': 'fixed' if flow_fixed_value >= 0.5 else 'flexible',
                        'history': [],
                        'availability': "08:00"  # default start time as string
                    }
                i += 1

            # Update session state worker_db
            st.session_state.worker_db = {}
            for idx, (worker_name, data) in enumerate(workers.items()):
                worker_id = f'worker_{idx+1}'
                st.session_state.worker_db[worker_id] = data

            st.success('Data pegawai berhasil dimuat dari CSV.')
        except Exception as e:
            st.error(f'Gagal memuat data pegawai dari CSV: {e}')

    # Antarmuka pengguna dengan Streamlit
    st.title('Manajemen Pekerja')


    # Form untuk menambahkan pekerja
    with st.form('add_worker_form'):
        st.subheader('Tambah Pekerja Baru')
        worker_id = st.text_input('ID Pekerja', help='Masukkan ID unik untuk pekerja, misalnya "worker_1"')
        name = st.text_input('Nama Pekerja', help='Masukkan nama lengkap pekerja')
        
        st.markdown("### Keterampilan")
        st.markdown("Masukkan persentase keterampilan untuk setiap jenis keterampilan berikut (0-100%).")
        bending = st.number_input('Bending (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Bending')
        gluing = st.number_input('Gluing (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Gluing')
        assembling = st.number_input('Assembling (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Assembling')
        edge_scrap = st.number_input('Edge scrap (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Edge scrap')
        open_paper = st.number_input('Open Paper (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Open Paper')
        quality_control = st.number_input('Quality Control (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Quality Control')
        skills = [bending/100, gluing/100, assembling/100, edge_scrap/100, open_paper/100, quality_control/100]

        favorites = st.text_input('Favorit (pisahkan dengan koma)', help='Masukkan preferensi tugas dari yang paling tidak disukai ke yang paling disukai, pisahkan dengan koma').split(',')
        preference = st.selectbox('Preferensi', ['fixed', 'flexible'], help='Pilih preferensi kerja: fixed atau flexible')
        history = st.text_area('Riwayat Pekerja (pisahkan dengan koma)', help='Masukkan riwayat tugas pekerja, pisahkan dengan koma').split(',')

        availability = st.selectbox('Start Time Availability', time_slots, index=0, help='Pilih waktu mulai ketersediaan pekerja')

        submit_button = st.form_submit_button('Tambah Pekerja')
        if submit_button:
            if worker_id and name:
                add_worker(worker_id, name, skills, favorites, preference, history, availability)
            else:
                st.error('ID Pekerja dan Nama Pekerja wajib diisi!')

    # Form untuk menghapus pekerja
    with st.form('delete_worker_form'):
        st.subheader('Hapus Pekerja')
        delete_worker_id = st.text_input('ID Pekerja yang akan dihapus', help='Masukkan ID pekerja yang ingin dihapus')
        delete_button = st.form_submit_button('Hapus Pekerja')
        if delete_button:
            if delete_worker_id:
                delete_worker(delete_worker_id)
            else:
                st.error('ID Pekerja wajib diisi!')

    # Form untuk memperbarui pekerja
    with st.form('update_worker_form'):
        st.subheader('Perbarui Pekerja')
        update_worker_id = st.text_input('ID Pekerja yang akan diperbarui', help='Masukkan ID pekerja yang ingin diperbarui')
        new_name = st.text_input('Nama Pekerja Baru', help='Masukkan nama baru pekerja')
        
        st.markdown("### Keterampilan Baru")
        st.markdown("Masukkan persentase keterampilan baru untuk setiap jenis keterampilan berikut (0-100%).")
        new_bending = st.number_input('Bending Baru (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Bending baru')
        new_gluing = st.number_input('Gluing Baru (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Gluing baru')
        new_assembling = st.number_input('Assembling Baru (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Assembling baru')
        new_edge_scrap = st.number_input('Edge scrap Baru (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Edge scrap baru')
        new_open_paper = st.number_input('Open Paper Baru (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Open Paper baru')
        new_quality_control = st.number_input('Quality Control Baru (%)', min_value=0, max_value=100, value=0, help='Persentase keterampilan Quality Control baru')
        new_skills = [new_bending/100, new_gluing/100, new_assembling/100, new_edge_scrap/100, new_open_paper/100, new_quality_control/100]

        new_favorites = st.text_input('Favorit Baru (pisahkan dengan koma)', help='Masukkan preferensi tugas baru, pisahkan dengan koma').split(',')
        new_preference = st.selectbox('Preferensi Baru', ['fixed', 'flexible'], help='Pilih preferensi kerja baru: fixed atau flexible')
        new_history = st.text_area('Riwayat Baru (pisahkan dengan koma)', help='Masukkan riwayat tugas baru, pisahkan dengan koma').split(',')

        new_availability = st.selectbox('Start Time Availability Baru', time_slots, index=0, help='Pilih waktu mulai ketersediaan pekerja')

        update_button = st.form_submit_button('Perbarui Pekerja')
        if update_button:
            if update_worker_id:
                update_worker(update_worker_id, new_name, new_skills, new_favorites, new_preference, new_history, new_availability)
            else:
                st.error('ID Pekerja wajib diisi!')

    # Menampilkan data pekerja yang ada
    st.subheader('Daftar Pekerja')
    for worker_id, worker_info in st.session_state.worker_db.items():
        availability_str = f", Availability Start Time: {worker_info['availability']}" if 'availability' in worker_info and worker_info['availability'] is not None else ""
        # Ensure skills are floats before formatting
        skills_formatted = []
        for s in worker_info['skills']:
            try:
                skill_float = float(s)
                skills_formatted.append(f"{skill_float:.0%}")
            except:
                skills_formatted.append(str(s))
        st.write(f"ID: {worker_id}, Nama: {worker_info['name']}, Keterampilan: {', '.join(skills_formatted)}{availability_str}")

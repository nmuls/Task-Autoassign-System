import matplotlib.pyplot as plt
import numpy as np
import plotly.figure_factory as ff
import pandas as pd
import streamlit as st

def display_worker_skills(worker_data):
    """Display worker skills as a bar chart"""
    skills = worker_data['skills']
    
    # Create a pandas dataframe for the skills
    skill_df = pd.DataFrame({
        'Skill': list(skills.keys()),
        'Level': list(skills.values())
    })
    
    # Sort by skill level
    skill_df = skill_df.sort_values('Level', ascending=False)
    
    # Display as a bar chart
    st.bar_chart(skill_df.set_index('Skill'))

def display_best_task_matches(worker, product_db, worker_name):
    """Display the best task matches for a worker"""
    from system import calculate_worker_task_match
    
    # Calculate match score for all tasks across all products
    matches = []
    
    for product_name, product_data in product_db.items():
        for task in product_data['tasks']:
            score = calculate_worker_task_match(worker, task)
            matches.append({
                'Product': product_name,
                'Task': task['name'],
                'Match Score': round(score * 100, 1)
            })
    
    # Convert to dataframe and sort
    match_df = pd.DataFrame(matches)
    match_df = match_df.sort_values('Match Score', ascending=False)
    
    # Display top matches
    st.dataframe(match_df, height=200)

def display_task_attributes(product_data, product_name):
    """Display task attributes for a product"""
    tasks = product_data['tasks']
    
    # Collect all unique attributes
    all_attributes = set()
    for task in tasks:
        all_attributes.update(task['attributes'].keys())
    
    # Create a matrix for the heatmap
    attr_matrix = []
    task_names = []
    
    for task in tasks:
        task_names.append(task['name'])
        row = []
        for attr in sorted(all_attributes):
            row.append(task['attributes'].get(attr, 0))
        attr_matrix.append(row)
    
    # Create a dataframe
    df = pd.DataFrame(attr_matrix, index=task_names, columns=sorted(all_attributes))
    
    # Display as a heatmap
    st.write(f"Task Attributes Heatmap for {product_name}")
    st.dataframe(df.style.background_gradient(cmap='viridis', axis=None))

def create_gantt_chart(schedule_data):
    """Create a Gantt chart visualization of the schedule"""
    if not schedule_data:
        return None
    
    # Process schedule data for Gantt chart
    df = []
    
    # Group tasks by worker and task
    task_groups = {}
    
    for item in schedule_data:
        # Skip idle tasks
        if item['status'] == 'idle':
            continue
        
        # Create a unique key for each task
        task_key = f"{item['worker_id']}_{item['product']}_{item['task_id']}_{item['task_name']}"
        
        if task_key not in task_groups:
            task_groups[task_key] = {
                'Task': f"{item['task_name']} - {item['worker_name']}",
                'Start': None,
                'Finish': None,
                'Resource': item['worker_name'],
                'Day': item['day']
            }
        
        # Parse time
        hours, minutes = map(int, item['time'].split(':'))
        current_time = hours + minutes/60
        
        # Set start time if not set
        if task_groups[task_key]['Start'] is None:
            task_groups[task_key]['Start'] = current_time
        
        # Always update finish time to the latest
        task_groups[task_key]['Finish'] = current_time + 0.5  # Each slot is 30 minutes
    
    # Convert to list
    for task_key, task_data in task_groups.items():
        df.append(task_data)
    
    # If no tasks, return None
    if not df:
        return None
    
    # Group by day
    df_by_day = {}
    for item in df:
        day = item['Day']
        if day not in df_by_day:
            df_by_day[day] = []
        
        # Copy item without day field
        new_item = item.copy()
        del new_item['Day']
        df_by_day[day].append(new_item)
    
    # Create a figure for each day
    fig = ff.create_gantt(
        df_by_day[1],  # Show first day by default
        index_col='Resource',
        show_colorbar=True,
        group_tasks=True,
        showgrid_x=True,
        showgrid_y=True,
        title=f"Production Schedule - Day 1"
    )
    
    # Set x-axis limits to 8AM - 4PM (8-16)
    fig.update_xaxes(range=[8, 16], title_text="Time (Hours)")
    
    # Set y-axis title
    fig.update_yaxes(title_text="Worker")
    
    # Customize height
    fig.update_layout(height=400, margin=dict(l=0, r=0, t=50, b=0))
    
    return fig

def display_daily_schedule(schedule_df, day):
    """Display the schedule for a specific day as a table"""
    # Filter for the given day
    day_df = schedule_df[schedule_df['day'] == day].copy()
    
    # Sort by time and worker
    day_df = day_df.sort_values(['time', 'worker_name'])
    
    # Clean up columns for display
    display_df = day_df[['time', 'worker_name', 'product', 'task_name', 'status']]
    display_df.columns = ['Time', 'Worker', 'Product', 'Task', 'Status']
    
    # Replace None with empty strings
    display_df = display_df.fillna('')
    
    # Display
    st.write(f"**Day {day} Schedule**")
    st.dataframe(display_df, height=400)
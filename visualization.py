import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from utils import get_time_from_slot, format_time_for_display

def display_task_attributes(schedule_data):
    """
    Display attributes of each task in the schedule.
    """
    if not schedule_data.get('schedule'):
        st.error("No schedule data to display.")
        return

    st.subheader("Production Schedule Details")
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(schedule_data['schedule'])
    
    # Display as a sortable table
    st.dataframe(df)
    
    # Display statistics
    st.subheader("Production Statistics")
    stats = schedule_data.get('stats', {})
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Tasks Assigned", f"{stats.get('total_tasks_assigned', 0)}/{stats.get('total_tasks_needed', 0)}")
    with col2:
        st.metric("Completion", f"{stats.get('completion_percentage', 0):.1f}%")
    with col3:
        st.metric("Days Needed", stats.get('days_needed', 0))
    
    # Display worker roles
    st.subheader("Worker Role Assignments")
    worker_roles = schedule_data.get('worker_roles', {})
    
    roles_df = pd.DataFrame({
        'Worker': [data['name'] for _, data in worker_roles.items()],
        'Assigned Role': [data['assigned_role'] for _, data in worker_roles.items()],
        'Score': [f"{data['score']:.1f}" for _, data in worker_roles.items()]
    })
    
    st.dataframe(roles_df)
    
    # Display unassigned tasks if any
    unassigned = schedule_data.get('unassigned_tasks', [])
    if unassigned:
        st.subheader("Unassigned Tasks")
        st.dataframe(pd.DataFrame(unassigned))

def visualize_schedule(schedule_data):
    """
    Visualize schedule using Gantt chart and display task information.
    """
    if not schedule_data or 'error' in schedule_data:
        st.error(schedule_data.get('error', "Failed to generate schedule."))
        return
    
    # Display schedule information
    display_task_attributes(schedule_data)
    
    # Create Gantt chart
    create_gantt_chart(schedule_data)

def create_gantt_chart(schedule_data):
    """
    Create a Gantt chart visualization of the production schedule.
    
    Args:
        schedule_data (dict): Dictionary containing schedule information
    """
    if not schedule_data or not schedule_data.get('schedule'):
        st.error("No schedule data to visualize")
        return
    
    schedule = schedule_data['schedule']
    days_needed = schedule_data.get('days_needed', 1)
    
    # Group by day
    days = set([task['day'] for task in schedule])
    
    # Create tabs for each day
    tabs = st.tabs([f"Day {day}" for day in sorted(days)])
    
    # Color mapping for products
    products = list(set([task['product'] for task in schedule]))
    colormap = plt.cm.get_cmap('tab10', len(products))
    product_colors = {product: (colormap(i)[0], colormap(i)[1], colormap(i)[2], 0.8)
                     for i, product in enumerate(products)}
    
    for i, day in enumerate(sorted(days)):
        day_tasks = [task for task in schedule if task['day'] == day]
        
        # Group by worker
        workers = sorted(set([(task['worker_id'], task['worker_name']) for task in day_tasks]), 
                         key=lambda x: x[1])
        
        # Create chart data
        with tabs[i]:
            # Display rebalancing info if any
            rebalanced_tasks = [task for task in day_tasks if task['assigned_role'] == 'rebalanced']
            if rebalanced_tasks:
                st.info(f"⚠️ {len(rebalanced_tasks)} tasks were rebalanced due to excessive repetition.")
            
            # Create a DataFrame for plotting
            chart_data = []
            for task in day_tasks:
                start_time = datetime.strptime(task['start_time'], '%H:%M')
                end_time = datetime.strptime(task['end_time'], '%H:%M')
                
                # Handle tasks that cross midnight
                if end_time < start_time:
                    end_time = end_time + timedelta(days=1)
                
                chart_data.append({
                    'Worker': f"{task['worker_name']} ({task['assigned_role']})",
                    'Task': f"{task['product']} - {task['task_name']}",
                    'Start': start_time.strftime('%H:%M'),
                    'End': end_time.strftime('%H:%M'),
                    'Product': task['product'],
                    'Role': task['assigned_role']
                })
            
            df = pd.DataFrame(chart_data)
            
            if not df.empty:
                # Plot using streamlit time_series chart
                st.subheader(f"Day {day} Schedule")
                
                # Create a detailed table view
                st.dataframe(df.sort_values(by=['Worker', 'Start']))
                
                # Create basic Gantt visualization
                fig, ax = plt.subplots(figsize=(12, 6))
                
                # Set up y-axis with worker names
                workers_list = sorted(df['Worker'].unique())
                ax.set_yticks(range(len(workers_list)))
                ax.set_yticklabels(workers_list)
                
                # Set up x-axis for time
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
                
                # Plot tasks as bars
                for idx, worker in enumerate(workers_list):
                    worker_tasks = df[df['Worker'] == worker]
                    
                    for _, task in worker_tasks.iterrows():
                        start = datetime.strptime(f"2023-01-01 {task['Start']}", '%Y-%m-%d %H:%M')
                        end = datetime.strptime(f"2023-01-01 {task['End']}", '%Y-%m-%d %H:%M')
                        
                        # Handle tasks crossing midnight
                        if end < start:
                            end = end + timedelta(days=1)
                        
                        duration = (end - start).total_seconds() / 3600  # in hours
                        
                        # Choose color
                        color = product_colors[task['Product']]
                        if task['Role'] == 'rebalanced':
                            edgecolor = 'red'
                            linewidth = 2
                        else:
                            edgecolor = 'black'
                            linewidth = 1
                        
                        # Plot bar
                        ax.barh(idx, duration, left=start, height=0.5,
                               color=color, edgecolor=edgecolor, linewidth=linewidth)
                        
                        # Add label
                        label = task['Product'].split()[-1]  # Just show short product name
                        ax.text(start + timedelta(hours=duration/2), idx, 
                               label, ha='center', va='center', fontsize=8)
                
                # Set limits and grid
                ax.set_xlim(datetime.strptime('2023-01-01 08:00', '%Y-%m-%d %H:%M'),
                           datetime.strptime('2023-01-01 16:00', '%Y-%m-%d %H:%M'))
                ax.grid(True, axis='x')
                
                ax.set_title(f"Day {day} Production Schedule")
                ax.set_xlabel("Time")
                
                # Add legend for products
                product_patches = [plt.Rectangle((0, 0), 1, 1, 
                                              color=product_colors[p]) for p in products]
                ax.legend(product_patches, products, loc='upper right')
                
                # Show plot
                st.pyplot(fig)
            else:
                st.info(f"No tasks scheduled for Day {day}")

def display_worker_schedule_detailed(schedule_data):
    """
    Display detailed worker schedule with task information.
    
    Args:
        schedule_data (dict): Dictionary containing schedule information
    """
    if not schedule_data or not schedule_data.get('schedule'):
        return
    
    schedule = schedule_data['schedule']
    worker_roles = schedule_data.get('worker_roles', {})
    
    st.subheader("Worker Schedules")
    
    # Group by worker
    workers = set([(task['worker_id'], task['worker_name']) for task in schedule])
    
    # Create tabs for each worker
    worker_tabs = st.tabs([f"{name}" for _, name in sorted(workers, key=lambda x: x[1])])
    
    for i, (worker_id, worker_name) in enumerate(sorted(workers, key=lambda x: x[1])):
        with worker_tabs[i]:
            worker_schedule = [task for task in schedule if task['worker_id'] == worker_id]
            
            # Group by day
            days = sorted(set([task['day'] for task in worker_schedule]))
            
            for day in days:
                day_tasks = [task for task in worker_schedule if task['day'] == day]
                
                # Sort by time
                day_tasks.sort(key=lambda x: x['time_slot'])
                
                st.subheader(f"Day {day}")
                
                # Create a table
                df = pd.DataFrame(day_tasks)
                
                # Select and rename columns for display
                columns = ['start_time', 'end_time', 'product', 'task_name', 'assigned_role', 'status']
                readable_columns = ['Start', 'End', 'Product', 'Task', 'Role', 'Status']
                
                if not df.empty and all(col in df.columns for col in columns):
                    display_df = df[columns].copy()
                    display_df.columns = readable_columns
                    
                    # Style the dataframe for better visualization
                    st.dataframe(display_df, 
                                use_container_width=True,
                                hide_index=True)
                else:
                    st.info("No tasks scheduled")
                
                # Count tasks by type for this worker and day
                task_counts = {}
                for task in day_tasks:
                    task_key = f"{task['product']}_{task['task_id']}"
                    task_counts[task_key] = task_counts.get(task_key, 0) + 1
                
                # Display statistics
                if task_counts:
                    st.caption("Task Distribution:")
                    for task_key, count in task_counts.items():
                        product, task_id = task_key.split('_', 1)
                        st.caption(f"• {product} - {task_id}: {count} slots")
# Task Autoassign System

A streamlit-based application for automatically assigning manufacturing tasks to workers based on their skills, preferences, and optimal workflow patterns.

## Overview

This system helps manufacturing facilities optimize their production schedules by intelligently matching workers to tasks based on:
- Worker skills and preferences
- Task requirements and dependencies
- Fixed vs. flow work style preferences
- Efficient task sequencing

## Features

- **Automated Task Assignment**: Algorithm to match workers with tasks based on skills and preferences
- **Fixed vs. Flow Role Assignment**: Identifies whether workers should specialize or move between tasks
- **Dependency Management**: Respects task prerequisites and manufacturing sequences
- **Schedule Visualization**: Interactive Gantt charts and daily schedules
- **Workload Balancing**: Redistributes tasks to avoid worker overload and minimize idle time

## Project Structure

- `app.py` - Main Streamlit application entry point
- `db.py` - Database initialization and management
- `system.py` - Core scheduling algorithm and logic
- `visualization.py` - Data visualization components
- `test.py` - Unit tests for core functionality
- `requirements.txt` - Python dependencies

## Installation

1. Clone the repository
2. Install dependencies:
```
pip install -r requirements.txt
```
3. Run the application:
```
streamlit run app.py
```

## Usage

1. Select products and quantities for your production order
2. Select available workers
3. Click "Generate Schedule"
4. Explore the generated schedule through the Gantt chart and daily views

## Algorithm

The task assignment algorithm uses a multi-factor approach:
1. Tasks are arranged by sequence number and prerequisites
2. Workers are classified as "fixed" (specializing) or "flow" (versatile)
3. Workers are matched to tasks based on skill compatibility
4. Fixed workers are given similar tasks across time slots when possible
5. Flow workers are assigned diverse tasks based on current production needs
6. Schedule is rebalanced to minimize idle time

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

MIT

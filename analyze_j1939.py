import glob
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from j1939Parser import J1939Parser

"""
Read in one of the J1939 data and use the J1939Parser to decode it. Then we will plot a subset of the decoded data, including RPM, torque, vehicle speed, fuel rate, fuel level. The x-axis will be time in seconds since the start of the data.
"""

if __name__ == "__main__":
    matplotlib.rc("font", family="DejaVu Sans") 
    parser = J1939Parser()
    
    data_files = glob.glob('data/j1939/*.csv')
    if not data_files:
        print("No J1939 data files found in data/j1939/")
        exit(1)
    
    data_file = data_files[0]
    data_points = []
    with open(data_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            time = float(row.get('Timestamp', 0))
            pgn = int(row.get('PGN', 0))
            hex_data = row.get('Data', '')
            data = bytearray.fromhex(hex_data) if hex_data else bytearray()
            data_points.append((time, pgn, data))
    
    # Sort by time
    data_points.sort(key=lambda x: x[0])
    start_time = data_points[0][0] if data_points else 0
    
    # Dictionaries for each parameter
    param_data = {
        'Engine Speed': [],
        'Actual Engine - Percent Torque': [],
        'Wheel-Based Vehicle Speed': [],
        'Fuel Rate (Liquid)': [],
        # 'Instantaneous Fuel Economy': [],
        'Fuel Level': []
    }
    
    for time, pgn, data in data_points:
        parsed = parser.parse_data(pgn, data)
        # rel_time = time - start_time
        rel_time = time
        for param_name in param_data:
            if param_name in parsed:
                value = parsed[param_name]['value']
                param_data[param_name].append((rel_time, value))
    
    # Plot
    fig, axs = plt.subplots(len(param_data), 1, figsize=(10, 5 * len(param_data)))
    if len(param_data) == 1:
        axs = [axs]  # Ensure axs is always a list
    names = list(param_data.keys())
    for i, name in enumerate(names):
        times_vals = param_data[name]
        if times_vals:
            times, vals = zip(*times_vals)
            axs[i].plot(times, vals, 'o-')
            axs[i].set_xlabel('Time (s)')
            axs[i].set_ylabel(name)
            axs[i].set_title(name)
        else:
            axs[i].set_title(f'{name} (no data)')
    
    plt.tight_layout()
    plt.savefig('j1939_analysis.png')
    print("Plot saved to j1939_analysis.png")
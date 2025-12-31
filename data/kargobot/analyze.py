import os
import pandas as pd
import matplotlib.pyplot as plt
import math

def analyze_one_csv(file_path, csv_file, data_dir):
    print(f"Reading {file_path}...")
    try:
        df = pd.read_csv(file_path)
        
        if 'timestamp-ns' in df.columns:
            # For rows with the same timestamp, use uniform interpolation to make them different
            # Example: 5 rows with same timestamp -> +0.0, +0.2, +0.4, +0.6, +0.8
            counts = df.groupby('timestamp-ns')['timestamp-ns'].transform('count')
            cumcounts = df.groupby('timestamp-ns').cumcount()
            df['timestamp-ns'] = df['timestamp-ns'] + cumcounts / counts
            x_axis = df['timestamp-ns']
            x_label = 'Timestamp'
        else:
            x_axis = df.index
            x_label = 'Sample Index'
        
        fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
        
        # Plot pitch
        if 'pitch-rad' in df.columns:
            axes[0].plot(x_axis, df['pitch-rad'] / math.pi * 180, label='pitch-degrees', color='blue')
            axes[0].set_ylabel('Pitch (degrees)')
            axes[0].set_title(f'Data Analysis - {csv_file}')
            axes[0].legend()
            axes[0].grid(ls="--")
        else:
            print(f"Column 'pitch-rad' not found in {csv_file}")

        # Plot speed
        speed_col = 'front_axle_spd-kph'
        if speed_col in df.columns:
            axes[1].plot(x_axis, df[speed_col], label='Speed (kph)', color='green')
            axes[1].set_xlabel(x_label)
            axes[1].set_ylabel('Speed (kph)')
            axes[1].legend()
            axes[1].grid(ls="--")
        else:
            print(f"Column '{speed_col}' not found in {csv_file}")
            print(f"Available columns: {df.columns.tolist()}")

        plt.tight_layout()
        output_plot = os.path.join(data_dir, f"{os.path.splitext(csv_file)[0]}_analysis.png")
        fig.savefig(output_plot)
        plt.close(fig)
        print(f"Saved plot to {output_plot}")
            
    except Exception as e:
        print(f"Error processing {csv_file}: {e}")


def analyze_data():
    data_dir = os.path.dirname(os.path.abspath(__file__))
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    if not csv_files:
        print("No CSV files found in", data_dir)
        return

    for csv_file in csv_files:
        file_path = os.path.join(data_dir, csv_file)
        analyze_one_csv(file_path, csv_file, data_dir)
        

if __name__ == "__main__":
    analyze_data()

import os
import pandas as pd
import matplotlib.pyplot as plt
import math
import numpy as np

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
            
            # Slice the data using time (seconds since start)
            # Adjust start_time and end_time to zoom into different time windows
            # start_time, end_time = 105 * 60,  135 * 60    # seconds
            start_time, end_time = 105 * 60,  135 * 60    # seconds
            start_time, end_time = 50 * 60,  75 * 60    # seconds
            # start_time, end_time = 0, 300 * 60    # seconds
            
            time_min = df['timestamp-ns'].min()
            relative_time = df['timestamp-ns'] - df['timestamp-ns'].min()
            mask = (relative_time >= start_time) & (relative_time <= end_time)
            # df = df[mask].reset_index(drop=True)
            df = df[mask]
            
            if df.empty:
                print(f"Warning: No data in the time range {start_time}-{end_time}s for {csv_file}")
                return

            x_axis = (df['timestamp-ns'] - time_min) / 60.0
            x_label = 'Time (minutes)'
        else:
            # Fallback to index slicing if timestamp is not available
            start_idx = 40000
            end_idx = 50000
            df = df.iloc[start_idx:end_idx].reset_index(drop=True)
            x_axis = df.index
            x_label = 'Sample Index'
        
        fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
        
        # Plot pitch
        if 'pitch-rad' in df.columns:
            pitch_vec = df['pitch-rad'] / math.pi * 180
            axes[0].plot(x_axis, pitch_vec, label='pitch-degrees', color='blue')
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

def prepare_model_data(df):
    # Required columns
    required_cols = [
        'front_axle_spd-kph', 
        'longitudinal_acc-m/s2', 
        'pitch-rad', 
        'act_eng_percent_trq-0~100', 
        'eng_spd'
    ]
    
    # Drop rows with NaNs in required columns
    df_clean = df.dropna(subset=required_cols).copy()
    
    # Pre-known constants (using 1.0 as placeholders as they weren't specified)
    rho = 1.225  # Air density (kg/m3)
    Cair = 0.538   # Aerodynamic drag area (m2)
    A = 9.7    # Frontal area (m2)
    c1 = A * Cair * rho / 2.0  # Aerodynamic drag coefficient

    m = 49000.0  # Vehicle mass (kg)
    g = 9.81     # Gravitational acceleration (m/s2)
    mu = 0.004  # Rolling resistance coefficient

    # Rolling resistance coefficient
    c2 = m * g * mu

    # Gravitational component coefficient
    c3 = m * g

    # Inertial component coefficient
    c4 = m
    
    # Vehicle speed in m/s
    v = df_clean['front_axle_spd-kph'] / 3.6
    # Acceleration in m/s2
    a = df_clean['longitudinal_acc-m/s2']
    # Pitch in rad
    theta = df_clean['pitch-rad']
    
    # Torque (Nm) - using 385 as T_max from user instruction
    T_max = 2500.0  # Maximum engine torque (Nm)
    torque = (df_clean['act_eng_percent_trq-0~100'] / 100.0) * T_max
    # Angular velocity (rad/s) from RPM
    omega = df_clean['eng_spd'] * math.pi / 30.0
    # Power (W)
    power = torque * omega
    
    # Model features: P = p1*c1*v^3 + p2*c2*cos(theta)*v + p3*c3*sin(theta)*v + p4*c4*a*v
    X = np.column_stack([
        c1 * (v**3),
        c2 * np.cos(theta) * v,
        c3 * np.sin(theta) * v,
        c4 * a * v
    ])
    
    return X, power

def estimate_and_test_model():
    data_dir = os.path.dirname(os.path.abspath(__file__))
    train_file_name = "2024-07-05-09-53-49_10030--去程.csv"
    test_file_name = "2024-07-05-15-46-42_10030--回程.csv"
    # train_file_name, test_file_name = test_file_name, train_file_name  # Swap for another testing
    
    train_path = os.path.join(data_dir, train_file_name)
    test_path = os.path.join(data_dir, test_file_name)
    
    if not os.path.exists(train_path) or not os.path.exists(test_path):
        print("Training or testing files missing for model estimation.")
        return

    print(f"Fitting model using {train_file_name}...")
    df_train = pd.read_csv(train_path)
    X_train, y_train = prepare_model_data(df_train)
    
    # Least squares fit
    params, residuals, rank, s = np.linalg.lstsq(X_train, y_train, rcond=None)

    print("residuals:", residuals)
    
    print("Estimated Parameters:")
    for i, p in enumerate(params, 1):
        print(f"  p{i}: {p:.6f}")
        
    print(f"\nTesting model using {test_file_name}...")
    df_test = pd.read_csv(test_path)
    X_test, y_test = prepare_model_data(df_test)
    
    y_pred = X_test @ params
    
    # Calculate performance metrics
    mse = np.mean((y_test - y_pred)**2)
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(y_test - y_pred))
    r2 = 1 - (np.sum((y_test - y_pred)**2) / np.sum((y_test - np.mean(y_test))**2))
    
    print(f"Performance on test set:")
    print(f"  RMSE: {rmse:.2f} W")
    print(f"  MAE: {mae:.2f} W")
    print(f"  R2 Score: {r2:.4f}")
    
    # Plot results
    plt.figure(figsize=(12, 6))
    idx = 10000
    plt.plot(y_test.values[:idx], label='Actual Power', alpha=0.7)
    plt.plot(y_pred[:idx], label='Predicted Power', alpha=0.7, linestyle='--')
    plt.title('Power Prediction: Actual vs Model (First 1000 samples of Test Set)')
    plt.xlabel('Sample Index')
    plt.ylabel('Power (W)')
    plt.legend()
    plt.grid(True, ls='--')
    
    output_plot = os.path.join(data_dir, "model_fitting_results.png")
    plt.savefig(output_plot)
    plt.close()
    print(f"Saved model comparison plot to {output_plot}")

def analyze_data():
    data_dir = os.path.dirname(os.path.abspath(__file__))
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    if not csv_files:
        print("No CSV files found in", data_dir)
        return

    for csv_file in csv_files:
        file_path = os.path.join(data_dir, csv_file)
        analyze_one_csv(file_path, csv_file, data_dir)
    
    # Run model estimation and testing
    estimate_and_test_model()
        

if __name__ == "__main__":
    analyze_data()

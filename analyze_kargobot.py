import os
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import matplotlib

# --- Constants for Vehicle Physics ---
g_vehicle_params = {
    "mass_kg": 49000.0,
    "frontal_area_m2": 9.7,
    "drag_area_m2": 0.538,
    "air_density_kgm3": 1.225,
    "rolling_resistance_factor": 0.004,
    "max_torque_nm": 2500.0,
    "gravity_ms2": 9.81,
}

def nonlinear_model(X, p1, p2, p3, p4, p5):
    """
    Nonlinear model for power prediction.
    P = max(0, P_hat)
    """
    acc = X[:, 0]
    v = X[:, 1]
    theta = X[:, 2]
    theta = theta - p5 * acc  # Adjust pitch if needed
    # offset = X[:, 3]

    # Unpack vehicle parameters
    m = g_vehicle_params["mass_kg"]
    drag_area = g_vehicle_params["drag_area_m2"]
    air_density = g_vehicle_params["air_density_kgm3"]
    mu = g_vehicle_params["rolling_resistance_factor"]
    g =  g_vehicle_params["gravity_ms2"]
    # T_MAX = vehicle_params["max_torque_nm"]

    # Calculate coefficients

    # Calculate individual forces (N)
    force_aero = 0.5 * air_density * drag_area * (v ** 2)
    force_roll = mu * m * g * np.cos(theta)
    force_grav = m * g * np.sin(theta)
    force_inertial = m * acc

    p_hat = p1 * force_aero * v + p2 * force_roll * v + p3 * force_grav * v + p4 * force_inertial * v

    return np.maximum(0, p_hat)


def calculate_physics_components(df, vehicle_params):
    """
    Calculate engine power and individual force components from raw data.
    """
    # Base physical variables
    v = df["front_axle_spd-kph"] / 3.6  # velocity in m/s
    a = df["longitudinal_acc-m/s2"]  # acceleration in m/s2
    ts = df["timestamp-ns"]
    acc = np.gradient(v, ts)  # Numerical differentiation
    theta = df["pitch-rad"]  # pitch in rad
    trq_pct = df["act_eng_percent_trq-0~100"]
    eng_spd_rpm = df["eng_spd"]

    # Unpack vehicle parameters
    m = vehicle_params["mass_kg"]
    drag_area = vehicle_params["drag_area_m2"]
    air_density = vehicle_params["air_density_kgm3"]
    mu = vehicle_params["rolling_resistance_factor"]
    g = vehicle_params["gravity_ms2"]
    T_MAX = vehicle_params["max_torque_nm"]

    # Calculate coefficients

    # Calculate individual forces (N)
    df["force_aero"] = 0.5 * air_density * drag_area * (v ** 2)
    df["force_roll"] = mu * m * g * np.cos(theta)
    df["force_grav"] = m * g * np.sin(theta)
    df["force_inertial"] = m * acc

    # Calculate individual forces (N)
    # df["force_aero"] = C_AERO * (v**2)
    # df["force_roll"] = C_ROLL * np.cos(theta)
    # df["force_grav"] = C_GRAV * np.sin(theta)
    # df["force_inertial"] = C_INERTIAL * a


    # Calculate engine power (W)
    torque = (trq_pct / 100.0) * T_MAX
    omega = eng_spd_rpm * math.pi / 30.0  # angular velocity in rad/s
    df["power_engine"] = torque * omega

    return df


def prepare_model_data(df, vehicle_params):
    """
    Clean data and prepare features/target for model fitting.
    """
    required_cols = [
        "front_axle_spd-kph",
        "longitudinal_acc-m/s2",
        "pitch-rad",
        "act_eng_percent_trq-0~100",
        "eng_spd",
    ]
    df = df.copy()

    # Handle duplicate timestamps with uniform interpolation
    counts = df.groupby("timestamp-ns")["timestamp-ns"].transform("count")
    cumcounts = df.groupby("timestamp-ns").cumcount()
    df["timestamp-ns"] = df["timestamp-ns"] + cumcounts / counts

    df = df.sort_values("timestamp-ns").reset_index(drop=True)
    ts = df["timestamp-ns"]
    v = df["front_axle_spd-kph"] / 3.6
    # acc = df_clean["longitudinal_acc-m/s2"]
    acc = np.gradient(v, ts)  # Numerical differentiation
    df["acc"] = acc

    df = df[df["front_axle_spd-kph"] > 0.1]  # Remove stationary data
    df = df[df["brk_pedal_pos"] == 0]  # Remove thebraking events if column exists
    df = df[df["trans_cur_gear"] != 0]  # Remove neutral gear if column exists
    df.reset_index(drop=True, inplace=True)

    # Drop rows with NaNs in required columns
    df_clean = df.dropna(subset=required_cols)
    if df_clean.empty:
        return np.empty((0, 5)), np.array([])

   
    theta = df_clean["pitch-rad"]
    acc = df_clean["acc"]
    v = df_clean["front_axle_spd-kph"] / 3.6
    avg_v = np.mean(v)
    print(f"Average Speed {avg_v * 3.6} (km/h):")


    # Feature matrix X: [P_aero_base, P_roll_base, P_grav_base, P_accel_base, Offset]
    # Feature matrix X: [acc, v, theta, offset]
    X = np.column_stack(
        [
            acc, 
            v,
            theta,
            np.ones(len(v)),
        ]
    )

    T_MAX = vehicle_params["max_torque_nm"]

    # Target y: Actual Engine Power
    torque = (df_clean["act_eng_percent_trq-0~100"] / 100.0) * T_MAX
    omega = df_clean["eng_spd"] * math.pi / 30.0
    y = torque * omega

    return X, y


def analyze_one_csv(file_path, csv_file, data_dir):
    """
    Process a single CSV file, calculate physics, and generate subplots.
    """
    print(f"Reading and analyzing {csv_file}...")
    try:
        df = pd.read_csv(file_path)

        if "timestamp-ns" in df.columns:
            # Handle duplicate timestamps with uniform interpolation
            counts = df.groupby("timestamp-ns")["timestamp-ns"].transform("count")
            cumcounts = df.groupby("timestamp-ns").cumcount()
            df["timestamp-ns"] = df["timestamp-ns"] + cumcounts / counts

            # Zoom into a specific time window (seconds since start)
            time_min_ns = df["timestamp-ns"].min()
            relative_time_sec = df["timestamp-ns"] - time_min_ns

            # Adjustable time window
            # start_time, end_time = 50 * 60, 75 * 60
            start_time, end_time = 55 * 60, 60 * 60
            mask = (relative_time_sec >= start_time) & (relative_time_sec <= end_time)
            df = df[mask].copy()

            if df.empty:
                print(f"Warning: No data in specified time range for {csv_file}")
                return

            x_axis = (df["timestamp-ns"] - time_min_ns) / 60.0
            x_label = "Time (minutes)"
        else:
            # Fallback for data without timestamps
            start_idx, end_idx = 40000, 50000
            df = df.iloc[start_idx:end_idx].copy()
            x_axis = np.arange(len(df))
            x_label = "Sample Index"

        # Calculate physics components if required columns exist
        required_cols = [
            "front_axle_spd-kph",
            "longitudinal_acc-m/s2",
            "pitch-rad",
            "act_eng_percent_trq-0~100",
            "eng_spd",
        ]
        if all(col in df.columns for col in required_cols):
            df = calculate_physics_components(df, g_vehicle_params)

        # Generate Subplots
        fig, axes = plt.subplots(7, 1, figsize=(12, 18), sharex=True)

        # 1. Pitch
        if "pitch-rad" in df.columns:
            axes[0].plot(x_axis, df["pitch-rad"] * 180 / math.pi, color="blue", label="Pitch")
            axes[0].set_ylabel("Pitch (deg)")
            axes[0].set_title(f"Data Analysis - {csv_file}")

        # 2. Speed
        if "front_axle_spd-kph" in df.columns:
            axes[1].plot(x_axis, df["front_axle_spd-kph"], color="green", label="Speed")
            axes[1].set_ylabel("Speed (kph)")

        # 3. Engine Power
        if "power_engine" in df.columns:
            axes[2].plot(x_axis, df["power_engine"] / 1000.0, color="red", label="Engine Power")
            axes[2].set_ylabel("Power (kW)")

        # 4. Aero Drag Force
        if "force_aero" in df.columns:
            axes[3].plot(x_axis, df["force_aero"], color="orange", label="Aero Drag")
            axes[3].set_ylabel("Aero Drag (N)")

        # 5. Gravitational Force
        if "force_grav" in df.columns:
            axes[4].plot(x_axis, df["force_grav"], color="purple", label="Grav Force")
            axes[4].set_ylabel("Grav Force (N)")

        # 6. Rolling Resistance Force
        if "force_roll" in df.columns:
            axes[5].plot(x_axis, df["force_roll"], color="brown", label="Roll Res")
            axes[5].set_ylabel("Roll Res (N)")

        # 7. Inertial Force
        if "force_inertial" in df.columns:
            axes[6].plot(x_axis, df["force_inertial"], color="gray", label="Inertial Force")
            axes[6].set_ylabel("Inertial (N)")
            axes[6].set_xlabel(x_label)

        for ax in axes:
            ax.grid(ls="--")
            ax.legend(loc="upper right")

        plt.tight_layout()
        output_plot = os.path.join(data_dir, f"{os.path.splitext(csv_file)[0]}_analysis.png")
        fig.savefig(output_plot)
        plt.close(fig)
        print(f"Saved analysis plot to {output_plot}")

    except Exception as e:
        print(f"Error processing {csv_file}: {e}")


def estimate_and_test_model():
    """
    Perform nonlinear regression to estimate model parameters and evaluate on test data.
    """
    data_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(data_dir, "data", "kargobot")
    train_file = "2024-07-05-09-53-49_10030--去程.csv"
    test_file = "2024-07-05-15-46-42_10030--回程.csv"

    train_path = os.path.join(data_dir, train_file)
    test_path = os.path.join(data_dir, test_file)

    if not (os.path.exists(train_path) and os.path.exists(test_path)):
        print("Training or testing files missing for model estimation.")
        return

    print(f"Fitting model using {train_file}...")
    df_train = pd.read_csv(train_path)
    X_train, y_train = prepare_model_data(df_train, g_vehicle_params)

    if X_train.size == 0:
        print("No valid data for model fitting.")
        return

    # Parameter constraints (p1-p5)
    # p1, p3: >= 0
    # p2, p4: constrained to very small values as per original script logic
    # bounds = ([0.0, 0.0, 0.0, 0.0, -np.inf], [np.inf, 1e-6, np.inf, 1e-6, np.inf])
    # bounds = ([0.0, 0.0, 0.0, 0.0, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf])
    bounds = ([-np.inf, -np.inf, -np.inf, -np.inf, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf])
    initial_guess = [1.0, 1.0, 1.0, 1.0, 1.0]

    try:
        params, _ = curve_fit(nonlinear_model, X_train, y_train, p0=initial_guess, bounds=bounds)
    except Exception as e:
        print(f"Nonlinear fit failed: {e}. Falling back to least squares.")
        params, _, _, _ = np.linalg.lstsq(X_train, y_train, rcond=None)

    print("Estimated Parameters (p1-p5):")
    for i, p in enumerate(params, 1):
        print(f"  p{i}: {p:.6f}")

    print(f"\nEvaluating model using {test_file}...")
    df_test = pd.read_csv(test_path)
    X_test, y_test = prepare_model_data(df_test, g_vehicle_params)

    if X_test.size == 0:
        print("No valid test data found. Using training data for visualization.")
        X_test, y_test = X_train, y_train

    y_pred = nonlinear_model(X_test, *params)

    # Performance metrics
    mse = np.mean((y_test - y_pred) ** 2)
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(y_test - y_pred))
    r2 = 1 - (np.sum((y_test - y_pred) ** 2) / np.sum((y_test - np.mean(y_test)) ** 2))

    print(f"Performance Metrics:")
    print(f"  RMSE: {rmse:.2f} W")
    print(f"  MAE: {mae:.2f} W")
    print(f"  R2 Score: {r2:.4f}")

    # Plot Comparison
    plt.figure(figsize=(12, 6))
    plt.plot(y_test[:10000], label="Actual Power", alpha=0.7)
    plt.plot(y_pred[:10000], label="Predicted Power", alpha=0.7, linestyle="--")
    plt.title("Power Prediction: Actual vs Model (First 1000 samples)")
    plt.xlabel("Sample Index")
    plt.ylabel("Power (W)")
    plt.legend()
    plt.grid(True, ls="--")

    output_plot = os.path.join(data_dir, "model_fitting_results.png")
    plt.savefig(output_plot)
    plt.close()
    print(f"Saved model comparison plot to {output_plot}")


def run_analysis():
    """
    Main entry point for data analysis and model estimation.
    """
    data_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(data_dir, "data", "kargobot")
    csv_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]
    matplotlib.use("Agg")  # Use non-interactive backend
    matplotlib.rc("font", family='Songti SC')
    # matplotlib.rc("font", family='STSong')  # For Chinese characters
    # matplotlib.rc("font", **{"sans-serif": ["SimSun", "Arial"]})

    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return

    # Process each CSV
    for csv_file in csv_files:
        file_path = os.path.join(data_dir, csv_file)
        analyze_one_csv(file_path, csv_file, data_dir)

    # Fit and evaluate model
    estimate_and_test_model()


if __name__ == "__main__":
    run_analysis()

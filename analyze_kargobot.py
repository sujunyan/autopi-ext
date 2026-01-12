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
    "drag_factor": 0.538,
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
    drag_factor = g_vehicle_params["drag_factor"]
    drag_area = g_vehicle_params["frontal_area_m2"]
    air_density = g_vehicle_params["air_density_kgm3"]
    mu = g_vehicle_params["rolling_resistance_factor"]
    g =  g_vehicle_params["gravity_ms2"]
    # T_MAX = vehicle_params["max_torque_nm"]

    # Calculate coefficients

    # Calculate individual forces (N)
    H = 1.2
    force_aero = 0.5 * (1-H*0.085) * air_density * drag_factor * drag_area * (v ** 2)
    force_roll = mu * m * g * np.cos(theta)
    force_grav = m * g * np.sin(theta)
    force_inertial = m * acc

    p_hat = p1 * force_aero * v + p2 * force_roll * v + p3 * force_grav * v + p4 * force_inertial * v
    # p_hat = p1 * force_aero * v + p2 * force_roll * v + p3 * force_grav * v + p4 * force_inertial * v

    return np.maximum(0, p_hat)


def calculate_physics_components(df, vehicle_params):
    """
    Calculate engine power and individual force components from raw data.
    """
    # Base physical variables
    v = df["front_axle_spd-kph"] / 3.6  # velocity in m/s
    a = df["longitudinal_acc-m/s2"]  # acceleration in m/s2
    ts = df["timestamp"]
    acc = np.gradient(v, ts)  # Numerical differentiation
    theta = df["pitch-rad"]  # pitch in rad
    trq_pct = df["act_eng_percent_trq-0~100"]
    eng_spd_rpm = df["eng_spd"]

    # Unpack vehicle parameters
    m = vehicle_params["mass_kg"]
    drag_factor = vehicle_params["drag_factor"]
    drag_area = vehicle_params["frontal_area_m2"]
    air_density = vehicle_params["air_density_kgm3"]
    mu = vehicle_params["rolling_resistance_factor"]
    g = vehicle_params["gravity_ms2"]
    T_MAX = vehicle_params["max_torque_nm"]

    # Calculate coefficients

    # Calculate individual forces (N)
    df["force_aero"] = 0.5 * air_density * drag_factor * drag_area * v * v
    # print(df["force_aero"].head())
    # print(v.head())
    # print(drag_factor)
    # print(air_density)
    # print((v*v).head())
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
    # counts = df.groupby("timestamp-ns")["timestamp-ns"].transform("count")
    # cumcounts = df.groupby("timestamp-ns").cumcount()
    # df["timestamp-ns"] = df["timestamp-ns"] + cumcounts / counts
    # Group by 'timestamp-ns' and average other columns
    df = df.groupby("timestamp-ns", as_index=False).mean()
    df = df.sort_values("timestamp-ns").reset_index(drop=True)

    df = df.sort_values("timestamp-ns").reset_index(drop=True)
    ts = df["timestamp-ns"]
    v = df["front_axle_spd-kph"] / 3.6
    # acc = df_clean["longitudinal_acc-m/s2"]
    acc = np.gradient(v, ts)  # Numerical differentiation
    df["acc"] = acc


    df = df[df["front_axle_spd-kph"] > 0.1]  # Remove stationary data
    df = df[df["brk_pedal_pos"] == 0]  # Remove thebraking events if column exists
    df = df[df["trans_cur_gear"] != 0]  # Remove neutral gear if column exists
    df = df[df["act_eng_percent_trq-0~100"] > 20.0]  # Remove idle engine data
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


def load_kargobot_data(file_path):
    # Check if the file is from the new enxin dataset
    df = pd.read_csv(file_path)

    if "enxin" in file_path:
        # Read CSV, skip empty columns
        df = df.loc[:, ~df.columns.str.match('Unnamed')]  # Remove unnamed columns
        # Map new headers to standard variable names
        column_map = {
            "timestamp": "timestamp",
            "/alpas/chassis/chassis_info_rx-motion_info.front_axle_spd": "velocity",
            "/alpas/chassis/chassis_info_rx-motion_info.longitudinal_acc": "acceleration",
            "/alpas/v2x/v2x_app/v2x_others_tx-control_info.fuel_rate": "fuel_rate",
            "/alpas/chassis/chassis_info_rx-fi_economy_info.fuel_rate_liquid": "fuel_rate",
            # velocity (front axle speed in kph)
            "/alpas/chassis/chassis_info_rx-motion_info.front_axle_spd": "front_axle_spd-kph",
            # longitudinal acceleration (m/s^2)
            "/alpas/chassis/chassis_info_rx-motion_info.longitudinal_acc": "longitudinal_acc-m/s2",
            # pitch (radian)
            "/cargo/localization/pose-pitch": "pitch-rad",
            # actual engine percent torque (0~100)
            "/alpas/chassis/chassis_info_rx-engine_info.act_eng_percent_trq": "act_eng_percent_trq-0~100",
            # engine speed
            "/alpas/chassis/chassis_info_rx-engine_info.eng_spd": "eng_spd",
            # Add more mappings as needed
            "/cargo/localization/pose-y" : "pose-y",
            "/cargo/localization/pose-x" : "pose-x",
            "/cargo/localization/pose-z" : "pose-z",
        }

        available_map = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=available_map)
    else:
        column_map = {
            "timestamp-ns": "timestamp",
            # Add more mappings as needed
            "front_axle_spd-kph" : "front_axle_spd-kph",
            "longitudinal_acc-m/s2" : "longitudinal_acc-m/s2",
            "pitch-rad" : "pitch-rad",
            "act_eng_percent_trq-0~100" : "act_eng_percent_trq-0~100",
            "eng_spd" : "eng_spd",
        }

        available_map = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=available_map)

        # Handle duplicate timestamps with uniform interpolation
        counts = df.groupby("timestamp")["timestamp"].transform("count")
        cumcounts = df.groupby("timestamp").cumcount()
        df["timestamp"] = df["timestamp"] + cumcounts / counts

    return df
        

def analyze_one_csv(file_path, csv_file, data_dir):
    """
    Process a single CSV file, calculate physics, and generate subplots.
    """

    df = load_kargobot_data(file_path)

    # Zoom into a specific time window (seconds since start)
    time_min = df["timestamp"].min()
    relative_time_sec = df["timestamp"] - time_min
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
    df['datetime'] = df['datetime'].dt.tz_convert('Asia/Shanghai')
    # print(list(df.columns))

    # Adjustable time window
    # start_time, end_time = 50 * 60, 75 * 60
    # start_time, end_time = 40 * 60, (40+150) * 60

    mask_by_time_flag = False
    if mask_by_time_flag:
        start_time, end_time = 45 * 60, (45+134) * 60
        mask = (relative_time_sec >= start_time) & (relative_time_sec <= end_time)
        df = df[mask].copy()
    else:
        # filter by location
        start_x, start_y =  9355.450582, -5481.516917
        end_x, end_y = 117352.6759, 9514.426308
        # Compute distances to start and end
        start_dist = np.sqrt((df["pose-x"] - start_x)**2 + (df["pose-y"] - start_y)**2)
        end_dist = np.sqrt((df["pose-x"] - end_x)**2 + (df["pose-y"] - end_y)**2)

        # Find indices of closest points
        start_idx = start_dist.idxmin()
        end_idx = end_dist.idxmin()
        # Ensure correct order
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        # Mask the DataFrame
        df = df.loc[start_idx:end_idx].copy()

    # print pose-x and pose-y at start and end
    print("Start Pose (x, y):", df["pose-x"].iloc[0], df["pose-y"].iloc[0])
    print("End Pose (x, y):", df["pose-x"].iloc[-1], df["pose-y"].iloc[-1])


    # x_axis = (df["timestamp"] - time_min) / 60.0
    x_axis = df["datetime"]
    x_label = "Time"

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
    fig, axes = plt.subplots(8, 1, figsize=(12, 18), sharex=True)

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

    # Add after the last force plot, before plt.tight_layout()
    if "fuel_rate" in df.columns:
        # Add a new subplot if needed
        # kg/h
        data = df["fuel_rate"] / 3600.0
        total = data.sum() * (df["timestamp"].iloc[1] - df["timestamp"].iloc[0])
        print(f"Total Fuel Consumed: {total:.2f} kg")
        axes[7].plot(x_axis, data, color="green", label="Fuel Rate")
        axes[7].set_ylabel("Fuel Rate")
        axes[7].set_xlabel(x_label)

    for ax in axes:
        ax.grid(ls="--")
        ax.legend(loc="upper right")

    plt.tight_layout()
    output_plot = os.path.join(data_dir, "figs", f"{os.path.splitext(csv_file)[0]}_analysis.png")
    fig.savefig(output_plot)
    plt.close(fig)
    print(f"Saved analysis plot to {output_plot}")



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
    plt.plot(y_test[:1000], label="Actual Power", alpha=0.7)
    plt.plot(y_pred[:1000], label="Predicted Power", alpha=0.7, linestyle="--")
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
    # data_dir = os.path.join(data_dir, "data", "kargobot")
    data_dir = os.path.join(data_dir, "data", "kargobot", "enxin")
    csv_files = [f for f in os.listdir(data_dir) if f.endswith(".csv")]
    matplotlib.use("Agg")  # Use non-interactive backend
    matplotlib.rc("font", family='Songti SC')
    # matplotlib.rc("font", family='STSong')  # For Chinese characters
    # matplotlib.rc("font", **{"sans-serif": ["SimSun", "Arial"]})

    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return

    # Process each CSV
    csv_files.sort()
    for csv_file in csv_files:
        pass
        # print(csv_file)
    idx=6
    csv_file = [
        "BAG_2026-01-06-08-14-53_10258-extractor.csv", #idx=0
        "BAG_2026-01-06-09-05-54_10258-extractor.csv", #idx=1
        "BAG_2026-01-06-10-11-18_10257-extractor.csv", #idx=2
        "BAG_2026-01-06-10-14-08_10258-extractor.csv", #idx=3
        "BAG_2026-01-06-14-06-05_10258-extractor.csv", #idx=4
        "BAG_2026-01-07-07-57-27_10257-extractor.csv", #idx=5 #0107-257 ma1 34.79kg
        "BAG_2026-01-07-08-02-33_10258-extractor.csv", #idx=6 #0107-258 ma1 35.57kg
        "BAG_2026-01-07-13-23-06_10258-extractor.csv", #idx=7 # 0107-258 ma2, need to merge
        "BAG_2026-01-07-16-01-10_10258-extractor.csv", #idx=8
        "BAG_2026-01-07-16-16-43_10257-extractor.csv", #idx=9 0107-257
        "BAG_2026-01-08-16-22-16_10258-extractor.csv", #idx=10
        "BAG_2026-01-08-18-44-25_10258-extractor.csv", #idx=11
        "BAG_2026-01-09-08-48-59_10151-extractor.csv", #idx=12 #0109-151 ma1, 30.92kg

        # "BAG_2026-01-06-10-11-18_10257-extractor.csv", #idx=0
        # "BAG_2026-01-09-08-48-59_10151-extractor.csv", #idx=1 
        # "BAG_2026-01-07-07-57-27_10257-extractor.csv", #idx=2
        # "BAG_2026-01-07-16-16-43_10257-extractor.csv", #idx=3 
        # "BAG_2026-01-07-08-02-33_10258-extractor.csv", #idx=4 
        # "BAG_2026-01-08-16-22-16_10258-extractor.csv", #idx=5
        # "BAG_2026-01-07-16-01-10_10258-extractor.csv", #idx=6 
        # "BAG_2026-01-06-08-14-53_10258-extractor.csv", #idx=7
        # "BAG_2026-01-06-09-05-54_10258-extractor.csv", #idx=8
        # "BAG_2026-01-06-10-14-08_10258-extractor.csv", #idx=9
        # "BAG_2026-01-06-14-06-05_10258-extractor.csv", #idx=10
        # "BAG_2026-01-07-13-23-06_10258-extractor.csv", #idx=11
        # "BAG_2026-01-08-18-44-25_10258-extractor.csv", #idx=12
    ][idx]
    file_path = os.path.join(data_dir, csv_file)
    analyze_one_csv(file_path, csv_file, data_dir)
    # for csv_file in csv_files:
    #     file_path = os.path.join(data_dir, csv_file)
    #     analyze_one_csv(file_path, csv_file, data_dir)
    #     break

    # Fit and evaluate model
    # estimate_and_test_model()


if __name__ == "__main__":
    run_analysis()

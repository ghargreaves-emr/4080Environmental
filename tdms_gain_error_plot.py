import os
from datetime import datetime
from nptdms import TdmsFile
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt

import re


def compute_gain_error_ppm(test_points, dut_meas):
    # Gain error in ppm comes from slope deviation from unity.
    X = np.asarray(test_points).reshape(-1, 1)
    y = np.asarray(dut_meas)
    reg = LinearRegression().fit(X, y)
    slope = reg.coef_[0]
    return (slope - 1) * 1_000_000


def serial_sort_key(serial):
    normalized = str(serial).strip()
    if normalized.lower().startswith('0x'):
        normalized = normalized[2:]
    try:
        return (0, int(normalized, 16), str(serial))
    except ValueError:
        # Fallback keeps stable lexical ordering for unexpected serial formats.
        return (1, str(serial))


def get_first_available_channel(group, channel_names):
    for channel_name in channel_names:
        if channel_name in group:
            return group[channel_name][:]
    joined = ", ".join(channel_names)
    raise KeyError(f"No channel found from candidates: {joined}")


def parse_filename(filename):
    name = filename[:-5].strip()
    # Normalize extra spaces and AM/PM spacing
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'\s+(AM|PM)$', r'_\1', name)
    name = name.replace('RH_Set_ ', 'RH_Set_')

    pattern = re.compile(
        r'^(?P<serial>[^_]+)_Temp_Set_(?P<temp>[^_]+)_RH_Set_(?P<rh>\d+)_(?P<month>\d+)_(?P<day>\d+)_(?P<year>\d+)_(?P<hour>\d+)_(?P<minute>\d+)_(?P<second>\d+)_(?P<am_pm>AM|PM)$'
    )
    match = pattern.match(name)
    if not match:
        raise ValueError(f"Unable to parse filename: {filename}")

    serial = match.group('serial')
    temp_set = match.group('temp')
    rh_set = match.group('rh')
    month = int(match.group('month'))
    day = int(match.group('day'))
    year = int(match.group('year'))
    hour = int(match.group('hour'))
    minute = int(match.group('minute'))
    second = int(match.group('second'))
    am_pm = match.group('am_pm')

    dt = datetime(year, month, day, hour, minute, second)
    if am_pm == 'PM' and hour != 12:
        dt = dt.replace(hour=hour + 12)
    elif am_pm == 'AM' and hour == 12:
        dt = dt.replace(hour=0)
    return serial, temp_set, rh_set, dt

def main():
    root_path = r"C:\temp\EnvironmentalTesting\Round2Data"
    if not os.path.exists(root_path):
        print(f"Error: Path '{root_path}' does not exist. Please verify the directory path.")
        return
    data = []

    # Collect every .tdms file up front so we can report progress while loading.
    tdms_files = []
    for subdir in os.listdir(root_path):
        serial_path = os.path.join(root_path, subdir)
        if os.path.isdir(serial_path):
            for file in os.listdir(serial_path):
                if file.endswith('.tdms'):
                    tdms_files.append((serial_path, file))

    total_files = len(tdms_files)
    print(f"Found {total_files} TDMS file(s) to process.")

    for idx, (serial_path, file) in enumerate(tdms_files, start=1):
        print(f"\r[{idx}/{total_files}] Loading {file[:60]}", end='', flush=True)
        filepath = os.path.join(serial_path, file)
        try:
            parsed_serial, temp_set, rh_set, timestamp = parse_filename(file)
            # Load TDMS file
            tdms_file = TdmsFile.read(filepath)
            # Assume data is in the first group
            group = tdms_file.groups()[0]
            chamber_temp = get_first_available_channel(
                group,
                ['Chamber Temperature 300V', 'Chamber Temperature']
            )
            chamber_rh = get_first_available_channel(
                group,
                ['Chamber RH% 300V', 'Chamber RH%']
            )
            avg_temp = np.mean(chamber_temp)
            avg_rh = np.mean(chamber_rh)

            ranges = [
                ('10V', ['Test Points 10V'], ['DUT Measurements 10V']),
                ('300V', ['Test Points 300V', 'Test Points'], ['DUT Measurements 300V', 'DUT Measurements'])
            ]

            for range_name, test_candidates, dut_candidates in ranges:
                test_col = next((col for col in test_candidates if col in group), None)
                dut_col = next((col for col in dut_candidates if col in group), None)
                if test_col is None or dut_col is None:
                    continue

                test_points = group[test_col][:]
                dut_meas = group[dut_col][:]
                gain_error = compute_gain_error_ppm(test_points, dut_meas)

                # Omit outliers outside the valid gain error window.
                if abs(gain_error) > 100:
                    print(
                        f"\nOmitting {range_name} point from {file}: "
                        f"gain error {gain_error:.2f} ppm exceeds +/-100 ppm"
                    )
                    continue

                data.append({
                    'timestamp': timestamp,
                    'serial': parsed_serial,
                    'range': range_name,
                    'gain_error': gain_error,
                    'avg_temp': avg_temp,
                    'avg_rh': avg_rh
                })
        except Exception as e:
            print(f"\nError processing {filepath}: {e}")

    print(f"\nDone. Loaded {len(data)} data point(s) from {total_files} file(s).")

    # Create DataFrame
    df = pd.DataFrame(data)
    if df.empty:
        print("No data found.")
        return
    df = df.sort_values(['serial', 'timestamp'])

    # Plot
    fig, ax1 = plt.subplots(figsize=(14, 8))

    # Gain error for each serial in ascending order.
    serials = sorted(df['serial'].unique(), key=serial_sort_key)

    # Assign a unique color per serial so 10V and 300V share the serial's color.
    colormap = plt.get_cmap('tab20' if len(serials) > 10 else 'tab10')
    serial_colors = {ser: colormap(idx % colormap.N) for idx, ser in enumerate(serials)}

    for ser in serials:
        ser_df = df[df['serial'] == ser]
        for range_name, linestyle, marker in [('10V', '--', 's'), ('300V', '-', 'o')]:
            range_df = ser_df[ser_df['range'] == range_name]
            if range_df.empty:
                continue
            ax1.plot(
                range_df['timestamp'],
                range_df['gain_error'],
                label=f'{ser} {range_name}',
                color=serial_colors[ser],
                linestyle=linestyle,
                marker=marker
            )

    ax1.set_xlabel('Time')
    ax1.set_ylabel('Gain Error - PPM')
    ax1.legend(loc='upper left')

    # Secondary y-axis for avg_temp (deduplicated by timestamp).
    env_df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp'])

    # Secondary y-axis for avg_temp
    ax2 = ax1.twinx()
    ax2.plot(env_df['timestamp'], env_df['avg_temp'], 'r-', label='Avg Chamber Temp', linewidth=2)
    ax2.set_ylabel('Avg Chamber Temperature (°C)', color='r')
    ax2.tick_params(axis='y', labelcolor='r')

    # Tertiary y-axis for avg_rh
    ax3 = ax1.twinx()
    ax3.spines['right'].set_position(('outward', 60))
    ax3.plot(env_df['timestamp'], env_df['avg_rh'], 'g-', label='Avg Chamber RH%', linewidth=2)
    ax3.set_ylabel('Avg Chamber RH (%)', color='g')
    ax3.tick_params(axis='y', labelcolor='g')

    plt.title('PXIe-4080 Gain Error (10V and 300V) and Chamber Conditions Over Time')
    fig.tight_layout()
    plt.savefig('gain_error_plot.png', dpi=300)
    plt.show()

if __name__ == "__main__":
    main()
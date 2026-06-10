# PXIe-4080 Gain Error Analysis (4080Environmental)

Parses National Instruments PXIe-4080 TDMS files and plots **gain error** for the
**10V** and **300V** ranges across all DUTs, alongside chamber temperature and
humidity over time.

## Contents

| File | Purpose |
| --- | --- |
| `tdms_gain_error_plot.ipynb` | Primary notebook — run top-to-bottom, edit inline |
| `tdms_gain_error_plot.py` | Standalone script version |
| `requirements.txt` | Pinned dependencies for reproducing the environment |
| `.gitignore` | Excludes `.venv/`, caches, checkpoints, generated PNG |

## Setup (per machine)

This project uses [`uv`](https://docs.astral.sh/uv/) to manage the virtual
environment. After cloning the repo:

```powershell
cd "01 Jpy Notebooks\4080Environmental"

# Create the virtual environment
uv venv .venv

# Install dependencies
uv pip install -r requirements.txt

# Register the Jupyter kernel used by the notebook
.\.venv\Scripts\python.exe -m ipykernel install --user --name 4080environmental --display-name "Python (4080Environmental)"
```

When you open `tdms_gain_error_plot.ipynb`, select the **Python (4080Environmental)**
kernel.

## Usage

### Notebook
Open `tdms_gain_error_plot.ipynb` and run the cells in order. Edit the
**Configuration** cell to point at your data:

- `ROOT_PATH` — folder containing one subfolder per DUT serial, each holding `.tdms` files
- `GAIN_ERROR_LIMIT_PPM` — outlier cutoff (points outside +/- this value are dropped)
- `OUTPUT_IMAGE` — filename for the saved plot

### Script
```powershell
.\.venv\Scripts\python.exe .\tdms_gain_error_plot.py
```

## Data layout

`ROOT_PATH` is expected to contain one subfolder per DUT serial number, with TDMS
files inside:

```
<ROOT_PATH>/
  2914BD3/
    2914BD3_Temp_Set_9C_RH_Set_ 40_6_3_2026_10_33_57 AM.tdms
    ...
  <serial2>/
    ...
```

TDMS data is **not** stored in this repo. Set `ROOT_PATH` per machine.

### Expected TDMS channels (first group)

| Range | Test points | DUT measurements |
| --- | --- | --- |
| 300V | `Test Points 300V` (fallback `Test Points`) | `DUT Measurements 300V` (fallback `DUT Measurements`) |
| 10V | `Test Points 10V` | `DUT Measurements 10V` |

Chamber channels: `Chamber Temperature 300V` (fallback `Chamber Temperature`) and
`Chamber RH% 300V` (fallback `Chamber RH%`).

## How gain error is computed

For each range, a linear fit of **DUT Measurements vs Test Points** is performed and
the gain error in ppm is:

```
gain_error_ppm = (slope - 1) * 1_000_000
```

## Plotting notes

- DUT serials are sorted in ascending **hexadecimal** order.
- For each serial, the 10V trace is drawn first, then 300V.
- Each serial has a unique color shared by both ranges:
  - 10V — dashed line, square markers
  - 300V — solid line, round markers
- Chamber temperature (red) and humidity (green) are overlaid on secondary axes,
  de-duplicated by timestamp.
- Points outside +/- `GAIN_ERROR_LIMIT_PPM` (default 100 ppm) are omitted.

# Slacking Off tool

A handy tool for slacking off.

While using Chrome's Picture-in-Picture (PiP) mode, this program activates your laptop's front-facing camera. If someone enters a designated area, it automatically closes the Chrome PiP window.

## Installation

First, run the following command to create a Python virtual environment:
```bash
python -m venv .venv
```

Next, run this command to export the YOLO26n OpenVINO model:

(You might need to `pip install` some libraries.)

```bash
python export_model.py
```

Then, activate the virtual environment:

```bash
Mac/Linux: source .venv/bin/activate
Windows: venv\Scripts\activate
```

## Usage

```bash
python monitor.py
```

A window showing the front-facing camera feed will open. Use your mouse to draw a box defining the ROI (Region of Interest).

- S: Start monitoring
- P: Pause / Resume detection
- R: Re-select the ROI
- Q: Exit the program

# Vectorworks Plugin Installation Guide

This guide explains how to install the openBIMForge Web Palette plugin for Vectorworks 2024.

## Prerequisites

- Vectorworks 2024 installed
- openBIMForge project folder on your computer
- PowerShell 5.1 or later

## Quick Installation

### Step 1: Run the Installer

Open PowerShell as Administrator and run:

```powershell
cd D:\path\to\openBIMForge
.\scripts\install_vectorworks_plugin.ps1
```

The installer will:
- Create a shortcut in Vectorworks Plug-ins directory
- Install Python paths for Vectorworks
- Preserve the project folder structure

### Step 2: Restart Vectorworks

Close and reopen Vectorworks to load the new plugin.

### Step 3: Verify Installation

In Vectorworks, open:

```text
Window > Palettes > Web Palettes > openBIMForge
```

The Web Palette should load the openBIMForge chat interface.

## Manual Installation

If the installer doesn't work or you prefer manual setup:

### Step 1: Locate Directories

**Source directory** (in your openBIMForge folder):
```text
openBIMForge\vectorworks_plugin\openBIMForge2024
```

**Target directory** (Vectorworks Plug-ins):
```text
%AppData%\Nemetschek\Vectorworks\2024\Plug-ins
```

### Step 2: Create Shortcut (Recommended)

1. Navigate to the Target directory in File Explorer
2. Right-click → New → Shortcut
3. Browse to the Source directory
4. Name it `openBIMForge2024`
5. Click Finish

**OR** copy the entire `openBIMForge2024` folder to the Target directory.

### Step 3: Install Python Shim

If you created a shortcut (not copied the folder), you need to install the Python shim:

1. Copy `openBIMForge2024\tool_agent` folder to:
   ```text
   %AppData%\Nemetschek\Vectorworks\2024\Plug-ins\tool_agent
   ```

2. Edit `tool_agent\vs_interface.py` and update the path:
   ```python
   # Find this line:
   OPENBIMFORGE_ROOT = Path(__file__).resolve().parents[3]

   # Replace with your actual path:
   OPENBIMFORGE_ROOT = Path(r"D:\your\actual\path\to\openBIMForge")
   ```

### Step 4: Install Python Paths

Run the Python path installer:

```powershell
cd D:\path\to\openBIMForge
.\scripts\install_vectorworks_paths.ps1
```

This creates a `.pth` file in Vectorworks Python Externals directory.

### Step 5: Restart Vectorworks

Close and reopen Vectorworks completely.

## How It Works

### Shortcut vs Copy

**Shortcut method** (recommended):
- Plugin files stay in the project folder
- Easy to update (just pull latest code)
- No need to copy files after updates

**Copy method**:
- Files are duplicated in Vectorworks directory
- Must recopy after any plugin updates
- Works if project folder moves

### Python Shim

The Python shim (`tool_agent/vs_interface.py`) is a lightweight proxy that:
- Intercepts calls from the Vectorworks `.vlb` plugin
- Redirects them to the openBIMForge Python code
- Handles the `__OPENBIMFORGE_RUN_ONCE__` command

### File Structure

After installation, Vectorworks Plug-ins directory should contain:

```text
%AppData%\Nemetschek\Vectorworks\2024\Plug-ins\
  openBIMForge2024\              # Shortcut or copied folder
    WebPaletteTUM.vlb            # Vectorworks native plugin
    WebPaletteTUM.vwr\           # Web Palette resources
    tool_agent\                  # Python shim (if copied)
  tool_agent\                    # Python shim (if using shortcut)
    __init__.py
    vs_interface.py
    speech2text.py
```

## Troubleshooting

### Web Palette doesn't appear

1. Check if shortcut/folder exists in Plug-ins directory
2. Verify Vectorworks was restarted after installation
3. Check Vectorworks Script Errors for import errors

### "Module not found" errors

1. Verify Python shim paths are correct
2. Run `install_vectorworks_paths.ps1` again
3. Check if openBIMForge folder exists at the specified path

### Plugin loads but doesn't work

1. Check Vectorworks Script Errors window
2. Look for `openbimforge_vs_interface_import_probe.json` in:
   ```text
   openBIMForge\forge_runtime\handoffs
   ```
3. If probe file exists, check its contents for error details

### After moving openBIMForge folder

1. Run installer again to update shortcut
2. Run `install_vectorworks_paths.ps1` to update Python paths
3. If using manual copy, recopy all files

## Uninstallation

To remove the plugin:

1. Delete the shortcut/folder from Vectorworks Plug-ins directory:
   ```text
   %AppData%\Nemetschek\Vectorworks\2024\Plug-ins\openBIMForge2024
   ```

2. Delete the Python shim folder:
   ```text
   %AppData%\Nemetschek\Vectorworks\2024\Plug-ins\tool_agent
   ```

3. Delete the Python paths file:
   ```text
   %AppData%\Nemetschek\Vectorworks\2024\Python Externals\openbimforge.pth
   ```

4. Restart Vectorworks

## Environment Variables

Optional environment variables for advanced configuration:

```powershell
# Override runtime root (default: openBIMForge\forge_runtime)
$env:OPENBIMFORGE_RUNTIME_ROOT = "D:\custom\runtime"

# Override Python command (default: python)
$env:OPENBIMFORGE_LAYOUT_PYTHON = "C:\Python39\python.exe"

# Override layout engine timeout (default: 900000ms = 15min)
$env:OPENBIMFORGE_LAYOUT_TIMEOUT_MS = "600000"
```

## Support

If you encounter issues:

1. Check Vectorworks Script Errors window
2. Look for probe files in `forge_runtime\handoffs`
3. Check Next.js console output
4. Review `forge_runtime\logs` for runtime errors

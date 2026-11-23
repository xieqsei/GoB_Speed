# Gob_Speed (GoB 分支版)

GoZ-alike tools for simple ZBrush<->Blender interchange.

本仓库是 GoB 的 **Gob_Speed 分支**：版本号跟随上游主线，后缀 `-Speed` 标明分支身份
（当前 `4.5.3-Speed`，基线上游 v4.5.3）。

分支在保留上游全部功能的基础上额外提供：

* **S导入**：向量化 `.GoZ` 解析，大网格导入更快（原版导入保持不变）
* **临时数据管理**子面板：统计 GoZ 中转目录占用、按白名单清理临时文件
* 中文对象名、UV 按面配对的可靠性修复

更新日志与专项说明见 [`docs/`](docs/)：`docs/CHANGELOG.md` 为总日志。

## Features
You can transfer:
* Objects (only meshes)
* Polypainting
* UVs
* Mask
* FaceSets
* Polygroup
* Diffuse map
* Normal map
* Displacement map

## GoB Setup
1. Download the latest "Source code (zip)" from "Releases"
2. Open Blender and Navigate to Edit > Preferences > Get Extensions
3. Uninstall any previous version of GoB by locating it in your extensions list, opening the drop down menu on the right side, and clicking "uninstall".
4. Install GoB by clicking the drop down menu found in the top right of the extensions window, and selecting "install from disk".
5. Navigate to and select the zip file downloaded in step One.
6. Locate GoB in Edit > Preferences > Add-ons to configure your settings.


## Usage
The addon adds two icons Import/Export to the top info panel:
* By clicking on the Export icon, you export the selected mesh objects into ZBrush.
* By clicking on the Import icon, you toggle autoloading mode. This will automatically load any models into blender that are exported from ZBrush via GoZ.
* By clicking on the Manual icon, you execute a one time import of the most recent model exported from ZBrush via GoZ.


# Acknowledgements
This script was originally written by user "Stunton" and posted [here on ZBrushCentral](http://www.zbrushcentral.com/showthread.php?127419-GoB-an-unofficial-GoZ-for-Blender).

It was also [posted on Blender's wiki](https://en.blender.org/index.php/Extensions:2.6/Py/Scripts/Import-Export/GoB_ZBrush_import_export) in the Import/Export Addons category, with the author listed as "ODe".

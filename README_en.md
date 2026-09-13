# MoreNifInput

## 1. Plugin Purpose

MoreNifInput is used to batch import NIF files from a large number of mods into Blender, and organize them by mod and model hierarchy within the same Blender window, making it easy to quickly preview the model relationships of many mods.

The plugin provides several cleanup settings to handle common mesh overlap and invalid mesh issues that occur during batch import. Most of these processes use deletion, as the primary goal of this plugin is previewing rather than editing and preserving.

The final result aims to present the mods and models in the library in a form that is as non-overlapping and grouped as possible. Due to significant differences in the directory structures of some mods, the results may be less than ideal in a few cases.

## 2. Development Environment

- Blender 5.1.2
- Windows 10 64-bit

The plugin has not been tested in other environments and may exhibit unknown issues.

## 3. User Workflow

1. Enter the path to the NIF library you want to process.
2. Select the output mode and click "Detect Count".
   - "Output by mod file level": Each mod's top-level folder is treated as one NIF group.
   - "Output by minimum file level": Each directory under meshes that directly contains NIF files is grouped separately, using nested collections.
3. Confirm the import settings and mesh layout.

![Separation of secondary parts description](separation.png)

The red box indicates the main part, and the blue box indicates the separated secondary parts.

4. Click "Start Import".

**When there are too many NIF files, the import time may be extremely long.**

5. Some nif files may fail to import. In this case, all nif files within the mod will be canceled from import, and a cube mesh will be used to indicate the error

## 4. Finding the File Location Corresponding to a Model

After selecting the target model in Blender, the collection hierarchy and collection names in the Outliner correspond to its file path.

## 5. Contributor

[https://github.com/FrozenTumbleweed](https://github.com/FrozenTumbleweed)

## 6. Open Source License

MIT: You only need to retain the copyright notice. You may use it in closed-source commercial projects with no other restrictions.

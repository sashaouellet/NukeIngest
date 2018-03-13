NukeIngest
====

A Python panel for Nuke that allows for the ingestion of footage to be converted into image sequence(s) in a shot format.

### About
The goal of this tool is to facilitate ingesting footage into a VFX pipeline. The project was initially built around using R3D footage, but definitely works with other formats. Certain operations can be done on incoming footage such as tagging with metadata, scaling, and creating additional proxy image sequences.

## Usage
Footage is imported on a per footage item basis, and then shots must be added. Each shot represents a frame range and increment (including frame handles, or padding on either end of the range). The shot translates into one EXR sequence to be outputted. The name/location of the outputted sequence is determined by the **Mappings** tab, which translates incoming naming schema into output ones. Variables can be injected with the `{VARIABLE_NAME}` format into either input or output values of the mapping table in order to generalize the ingestion process.

Other than manually importing footage and adding shots, the tool provides EDL (Edit Decision List) support. Specify a root directory where footage is located, import the EDL and the footage is automatically imported with the appropriate shots created. Furthermore, mappings can be read directly from a CSV (Comma Separated Value) file.

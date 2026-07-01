# NACHA Return Files

Sample return files consumed by the ReturnFileAgent.

Record structure:

- `1` File Header
- `5` Batch Header
- `6` Returned Entry Detail
- `7` Return Addenda (addenda type `99` carries return reason code and
  original trace number)
- `8` Batch Control
- `9` File Control

Real fixtures are added in a later prompt.

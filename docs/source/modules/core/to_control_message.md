<!--
SPDX-FileCopyrightText: Copyright (c) 2022-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

## ToControlMessage Module

This module converts `MessageMeta` to a `ControlMessage`.

### Configurable Parameters

| Parameter  | Type                | Description                                          | Example Value | Default Value |
|------------|---------------------|-------------------------------------------------------|---------------|---------------|
| `tasks`     | Array of Dictionaries | Control message tasks configuration                                  | `[{ "type": "inference", "properties": {} }]` | `None`        |
| `meta_data` | Dictionary          | Control message metadata configuration                              | `{"data_type": "streaming"}`               | `None`        |

### Example JSON Configuration

```json
{
  "meta_data": {
    "data_type": "streaming"
  },
  "tasks": [
    {
      "type": "inference",
      "properties": {}
    }
  ]
}
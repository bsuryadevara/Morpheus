/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#pragma once

#include "morpheus/io/data_loader.hpp"

namespace morpheus {
#pragma GCC visibility push(default)
/**
 * @brief Very simple raw data loader that takes payload data on the control message and returns it
 *
 */
class GRPCDataLoader : public Loader
{
  public:
    GRPCDataLoader()  = default;
    ~GRPCDataLoader() = default;

    std::shared_ptr<MessageControl> load(std::shared_ptr<MessageControl> message) final;
};
#pragma GCC visibility pop
}  // namespace morpheus
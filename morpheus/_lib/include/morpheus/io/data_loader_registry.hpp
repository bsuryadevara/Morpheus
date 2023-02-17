/**
 * SPDX-FileCopyrightText: Copyright (c) 2021-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
#include "morpheus/objects/factory_registry.hpp"

#include <mrc/utils/type_utils.hpp>
#include <pybind11/pybind11.h>

#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <string>

namespace morpheus {
#pragma GCC visibility push(default)

using LoaderRegistry = FactoryRegistry<Loader>;  // NOLINT

struct LoaderRegistryProxy
{
    static void register_proxy_factory_fn(
        const std::string& name,
        std::function<std::shared_ptr<MessageControl>(std::shared_ptr<MessageControl>)> proxy_constructor,
        bool throw_if_exists = true);

    static void register_factory_cleanup_fn(const std::string& name);
};
}  // namespace morpheus

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

#include <map>
#include <memory>

namespace morpheus {

class MessageControl;
class MessageMeta;

class Loader
{
  public:
    virtual ~Loader() = default;

    virtual std::shared_ptr<MessageMeta> load_data(const MessageControl& message) = 0;
};

class DataLoader
{
  public:
    DataLoader()  = default;
    ~DataLoader() = default;

    // Probably a MessageMeta?
    std::shared_ptr<MessageMeta> load(const MessageControl& control_message);

    void register_loader(const std::string& loader_id, std::unique_ptr<Loader> loader);

    void remove_loader(const std::string& loader_id);

  private:
    std::map<std::string, std::unique_ptr<Loader>> m_loaders;
};
}  // namespace morpheus
#ifndef EXAMPLES_DELEGATION_DEMO_SHARED_DELEGATION_FILES_H_
#define EXAMPLES_DELEGATION_DEMO_SHARED_DELEGATION_FILES_H_

#include <filesystem>
#include <string>
#include <vector>

#include "examples/delegation_demo/shared/types.h"
#include "examples/mdoc_anoncred/shared/types.h"

namespace proofs {

// ---- policy.json 读写 ----

// 将 Policy 写成格式化的 JSON 文件
bool WritePolicyJson(const std::filesystem::path& path,
                     const Policy& policy,
                     std::string* err);

// 从 JSON 文件读取 Policy
bool ReadPolicyJson(const std::filesystem::path& path,
                    Policy* policy,
                    std::string* err);

// ---- delegation/ 目录读写 ----

// 将委托目录写出：包含凭证材料（holder）+ Agent 密钥 + 委托签名 + 策略
// holder:         原始凭证（从 Alice 的 holder/ 目录读取）
// agent_pkx/pky:  Agent 临时公钥 hex（含 0x 前缀）
// agent_sk:       Agent 临时私钥 hex（含 0x 前缀）
// del_msg_hex:    委托消息摘要 hex（含 0x 前缀）
// del_sig_hex:    委托签名 hex（含 0x 前缀）
// policy:         委托策略
// allowed_claims: 筛选后的 claims（仅 policy 允许的）
bool WriteDelegationDir(const std::filesystem::path& dir,
                        const HolderMdoc& holder,
                        const std::string& agent_pkx_hex,
                        const std::string& agent_pky_hex,
                        const std::string& agent_sk_hex,
                        const std::string& del_msg_hex,
                        const std::string& del_sig_hex,
                        const Policy& policy,
                        const std::vector<ReaderClaim>& allowed_claims,
                        std::string* err);

// 从委托目录读取所有材料
bool ReadDelegationDir(const std::filesystem::path& dir,
                       HolderMdoc* holder,
                       std::string* agent_pkx_hex,
                       std::string* agent_pky_hex,
                       std::string* agent_sk_hex,
                       std::string* del_msg_hex,
                       std::string* del_sig_hex,
                       Policy* policy,
                       std::string* err);

// ---- delegation_token.json 读写 ----
// Module C 写出，Module D 读入

bool WriteDelegationTokenJson(const std::filesystem::path& path,
                              const std::string& agent_pkx_hex,
                              const std::string& agent_pky_hex,
                              const std::string& del_msg_hex,
                              const std::string& del_sig_hex,
                              const std::string& agent_sig_hex,
                              const std::string& device_pkx_hex,
                              const std::string& device_pky_hex,
                              const Policy& policy,
                              std::string* err);

bool ReadDelegationTokenJson(const std::filesystem::path& path,
                             std::string* agent_pkx_hex,
                             std::string* agent_pky_hex,
                             std::string* del_msg_hex,
                             std::string* del_sig_hex,
                             std::string* agent_sig_hex,
                             std::string* device_pkx_hex,
                             std::string* device_pky_hex,
                             Policy* policy,
                             std::string* err);

}  // namespace proofs

#endif  // EXAMPLES_DELEGATION_DEMO_SHARED_DELEGATION_FILES_H_

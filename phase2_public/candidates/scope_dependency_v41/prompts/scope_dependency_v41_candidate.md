## 范围依赖 v4.1 候选：完整替换 decision_basis 协议
以下 schema 是本次 decision_basis 的唯一字段/类型/枚举规范，替代前文该对象的
旧版结构；其他外层输出字段、法源准入、地域/时效、引用及人工复核要求保持有效。
不得输出 schema 外字段。所有 required=true 字段必须填写，无法完成检查时不编造
completed_check；check 名称与 comparison 均必填，不能用一个字段替代另一个。
只读取运行端 review_task_contract_v41.scope_spec，不自行扩大或缩小任务。
把 input_scope_sha256 原样复制到 task_scope_sha256。

先判定要求是否在当前项目/子问题实际生效，再判断其数值、年份、数量是否缺失。
模板有某栏不等于强制提交；有两个措辞不等于已证实冲突。缺少实际真实性验证、
最终递交包或后续履行证据，不自动阻断已锁定的文本核对。
但实际提交核查、完整期限、专项合规等当前任务的决定性材料仍须保留为阻断。

严格区分三层：
1. kind/dependency_key 说明缺什么材料。不得把“范围外”写成材料种类。
2. task_relation/reason/counterfactual_impact 解释为什么影响当前子结论。
3. 输出分组由 gate 生成。不得在模型 gap 中填 output_group 或自行宣称已放行。
真正阻断须绑定 required_claims 中已声明的依赖及子结论，解释哪一步不能完成。
有具体条款解释冲突时提供 trigger_evidence 原文定位；泛泛无法确保不存在任何
补遗只是待澄清关系，不自动成为关键法源或当前条款缺口。
范围外须是锁定配置明确排除、不影响任何子结论、false和空claim数组同时满足。
若锁定配置漏列潜在必要依赖，或材料类别/关系尚不清楚，提交范围复核，不改任务。
一个记录混合整包、真实性、具体更正、数值等事项时必须分别列项。
关系无法确定用 scope_unresolved；不能静默当作法律 U，也不得把未知变成 N。

text_observation 只记录有定位的输入事实，无独立法规支持能力；
legal_comparison 绑定准入法条与所支持的当前子结论，说明适用前提和实际比较。
单有一条引文、一般性法条、supplement或“未发现冲突”不足以证明范围内N。
输出理由、结论、差异和建议供人复核，不输出内部思维链。
范围外事项仍可见，不表示已经满足。整体仍需要人工二次审核。

以下是机器可读字段说明（自同一 schema 自动生成）：

{
  "basis": {
    "answerability": {
      "description": "关系未解决必须用 scope_unresolved，而非法律 U。",
      "enum": [
        "sufficient",
        "decisive_gap",
        "scope_unresolved"
      ],
      "required": true,
      "type": "text"
    },
    "bounded_conclusion": {
      "description": "当前问题内的实质结论，不证明总体合规。",
      "required": true,
      "type": "text"
    },
    "completed_checks": {
      "description": "已完成观察/法规比对；U 可为空，不伪造完成项。",
      "required": true,
      "type": "checks"
    },
    "gaps": {
      "description": "每项仅一种材料依赖；混合事项拆开，未知保持未知。",
      "required": true,
      "type": "gaps"
    },
    "review_question": {
      "description": "原样复制已锁定问题。",
      "required": true,
      "type": "text"
    },
    "review_target": {
      "description": "对应锁定任务模式。",
      "enum": [
        "textual_pre_review",
        "document_response",
        "document_completeness",
        "actual_conduct"
      ],
      "required": true,
      "type": "text"
    },
    "task_scope_sha256": {
      "description": "原样复制 review_task_contract_v41.input_scope_sha256。",
      "required": true,
      "type": "text"
    }
  },
  "check": {
    "check": {
      "description": "必须填写具体检查名称；comparison不能代填。",
      "required": true,
      "type": "text"
    },
    "check_id": {
      "description": "本单元内唯一检查编号。",
      "required": true,
      "type": "text"
    },
    "check_kind": {
      "description": "观察不作为独立法律依据。",
      "enum": [
        "text_observation",
        "legal_comparison"
      ],
      "required": true,
      "type": "text"
    },
    "claim_ids": {
      "description": "对应 required_claims；观察必须为空，法规比对不可为空。",
      "required": true,
      "type": "strings"
    },
    "comparison": {
      "description": "具体说明原文与要求的相同/差异及适用前提，不能只列法条。",
      "required": true,
      "type": "text"
    },
    "document_fragments": {
      "description": "可选，跨段时每段单独精确定位，2–8项。",
      "required": false,
      "type": "fragments"
    },
    "document_locator": {
      "description": "精确定位；多片段定位用分号连接。",
      "required": true,
      "type": "text"
    },
    "document_quote": {
      "description": "所给原文精确引用；多片段为逐项换行连接。",
      "required": true,
      "type": "text"
    },
    "legal_chunk_ids": {
      "description": "只填实际准入的法条；观察必须为空数组。",
      "required": true,
      "type": "strings"
    }
  },
  "dependency_kind_pairs": {
    "actual_performance": [
      "future_performance_unverified"
    ],
    "applicable_rule": [
      "key_legal_source_missing"
    ],
    "authenticity": [
      "authenticity_unverified"
    ],
    "comparison_operand": [
      "comparison_value_missing"
    ],
    "current_clause_context": [
      "input_evidence_missing",
      "required_document_missing"
    ],
    "other_undetermined": [
      "material_type_undetermined"
    ],
    "readability": [
      "unreadable_evidence"
    ],
    "regulatory_applicability": [
      "decisive_applicability_missing"
    ],
    "submission_package_completeness": [
      "input_evidence_missing",
      "required_document_missing"
    ]
  },
  "fragment": {
    "document_locator": {
      "description": "该片段唯一输入定位。",
      "required": true,
      "type": "text"
    },
    "document_quote": {
      "description": "单一片段精确原文。",
      "required": true,
      "type": "text"
    }
  },
  "gap": {
    "affected_claim_ids": {
      "description": "决定性缺口须绑定已声明且需要该依赖的子结论。",
      "required": true,
      "type": "strings"
    },
    "blocks_current_question": {
      "description": "必须与任务关系一致；false 不构成放行依据。",
      "required": true,
      "type": "bool"
    },
    "counterfactual_impact": {
      "description": "若材料缺失/补全，哪一步判断不能完成/会改变；范围外说明为何不改变当前比对。",
      "required": true,
      "type": "text"
    },
    "dependency_key": {
      "description": "缺失材料所属的一种依赖。",
      "enum": [
        "submission_package_completeness",
        "authenticity",
        "actual_performance",
        "current_clause_context",
        "applicable_rule",
        "regulatory_applicability",
        "comparison_operand",
        "readability",
        "other_undetermined"
      ],
      "required": true,
      "type": "text"
    },
    "dependency_trigger": {
      "description": "来源是任务明确要求、已观察冲突还是泛化猜测。",
      "enum": [
        "locked_requirement",
        "observed_context_conflict",
        "explicit_scope_exclusion",
        "generic_unverified_possibility",
        "undetermined"
      ],
      "required": true,
      "type": "text"
    },
    "detail": {
      "description": "只说明缺什么，不混合整包、真实性、补遗、金额等不同事项。",
      "required": true,
      "type": "text"
    },
    "gap_id": {
      "description": "本单元内唯一缺口编号。",
      "required": true,
      "type": "text"
    },
    "kind": {
      "description": "材料/证据状态，不使用范围外作为材料类型。",
      "enum": [
        "authenticity_unverified",
        "comparison_value_missing",
        "decisive_applicability_missing",
        "future_performance_unverified",
        "input_evidence_missing",
        "key_legal_source_missing",
        "material_type_undetermined",
        "required_document_missing",
        "unreadable_evidence"
      ],
      "required": true,
      "type": "text"
    },
    "reason": {
      "description": "说明该材料与当前子结论的关系，不写泛泛补查理由。",
      "required": true,
      "type": "text"
    },
    "task_relation": {
      "description": "为什么与锁定任务有关。",
      "enum": [
        "decisive_for_claim",
        "outside_locked_scope",
        "undetermined"
      ],
      "required": true,
      "type": "text"
    },
    "trigger_evidence": {
      "description": "观察到具体冲突时必须给出原文定位；其他情形可为空数组。",
      "required": true,
      "type": "pointers"
    }
  },
  "gate_owned_output_groups": [
    "blocking_gap",
    "out_of_scope_item",
    "scope_review_item"
  ],
  "mechanical_aliases": {
    "check": {
      "check_name": "check"
    }
  },
  "version": "scope-dependency-v4.1-candidate"
}
以下仅为协议合成示例，法条/定位/哈希占位符不可复制到真实输出；非法律结论：
{
  "pure_outside_item": {
    "review_question": "合成问题：承诺是否回应文字要求？",
    "review_target": "document_response",
    "answerability": "sufficient",
    "task_scope_sha256": "COPY_RUNTIME_HASH_NOT_THIS_PLACEHOLDER",
    "completed_checks": [
      {
        "check_id": "CK1",
        "check_kind": "legal_comparison",
        "check": "合成承诺文字与合成规则比对",
        "document_quote": "合成示例：申请人承诺提供有效证明。",
        "document_locator": "SYN-p001-b001",
        "legal_chunk_ids": [
          "SYN-law-1"
        ],
        "claim_ids": [
          "C1"
        ],
        "comparison": "合成情景中已给文字回应已给要求；不证明真实递交或法律正确。"
      }
    ],
    "bounded_conclusion": "仅限合成已给文字比对，不认证实际提交。",
    "gaps": [
      {
        "gap_id": "G1",
        "kind": "input_evidence_missing",
        "dependency_key": "submission_package_completeness",
        "detail": "最终递交包完整性尚未核验。",
        "task_relation": "outside_locked_scope",
        "affected_claim_ids": [],
        "blocks_current_question": false,
        "reason": "合成锁定配置明确排除整包核查，C1只比较已给文字。",
        "counterfactual_impact": "完整包状态不改变已给承诺与要求的文本关系。",
        "dependency_trigger": "explicit_scope_exclusion",
        "trigger_evidence": []
      }
    ]
  },
  "genuine_blocking_gap": {
    "review_question": "合成问题：承诺是否回应文字要求？",
    "review_target": "document_response",
    "answerability": "decisive_gap",
    "task_scope_sha256": "COPY_RUNTIME_HASH_NOT_THIS_PLACEHOLDER",
    "completed_checks": [],
    "bounded_conclusion": "合成锁定C1需要项目金额完成上限核算，现无法核算；保留U。",
    "gaps": [
      {
        "gap_id": "G1",
        "kind": "comparison_value_missing",
        "dependency_key": "comparison_operand",
        "detail": "计算上限需要的项目金额未提供。",
        "task_relation": "decisive_for_claim",
        "affected_claim_ids": [
          "C1"
        ],
        "blocks_current_question": true,
        "reason": "合成C1明确要求比较数额上限，其required_dependencies含comparison_operand。",
        "counterfactual_impact": "没有金额分母无法计算并比较上限，补全后才可作答。",
        "dependency_trigger": "locked_requirement",
        "trigger_evidence": []
      }
    ]
  }
}

// Map of known block types to render functions
const renderers = {
  heading: renderHeading,
  paragraph: renderParagraph,
  bullet_list: renderBulletList,
  card: renderCard,
  section: renderSection,
};

// Recursive render function
function renderBlocks(blocks) {
  const container = document.createElement("div");
  container.classList.add("blocks-container");

  blocks.forEach((block) => {
    const renderFn = renderers[block.type] || renderUnknown;
    const el = renderFn(block);
    container.appendChild(el);
  });

  return container;
}

/* ----------------------------
   Individual Block Renderers
---------------------------- */
function renderHeading(block) {
  const el = document.createElement("div");
  el.classList.add("block-heading");
  el.setAttribute("data-level", block.level || 2);
  el.textContent = block.text || "";
  return el;
}

function renderParagraph(block) {
  const el = document.createElement("div");
  el.classList.add("block-paragraph");
  el.textContent = block.text || "";
  return el;
}

function renderBulletList(block) {
  const ul = document.createElement("ul");
  ul.classList.add("block-bullet-list");
  (block.items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = typeof item === "string" ? item : item.text || "";
    ul.appendChild(li);
  });
  return ul;
}

function renderCard(block) {
  const card = document.createElement("div");
  card.classList.add("block-card");

  if (block.title) {
    const title = document.createElement("div");
    title.classList.add("card-title");
    title.textContent = block.title;
    card.appendChild(title);
  }

  if (block.subtitle) {
    const subtitle = document.createElement("div");
    subtitle.classList.add("card-subtitle");
    subtitle.textContent = block.subtitle;
    card.appendChild(subtitle);
  }

  // Nested blocks inside card
  if (block.blocks) {
    const nested = renderBlocks(block.blocks);
    nested.classList.add("nested-blocks");
    card.appendChild(nested);
  }

  // Optional bullet list
  if (block.bullets) {
    const ul = document.createElement("ul");
    block.bullets.forEach((b) => {
      const li = document.createElement("li");
      li.textContent = b;
      ul.appendChild(li);
    });
    card.appendChild(ul);
  }

  return card;
}

function renderSection(block) {
  const section = document.createElement("div");
  section.classList.add("block-section");

  if (block.title) {
    const title = document.createElement("div");
    title.classList.add("block-section-title");
    title.textContent = block.title;
    section.appendChild(title);
  }

  const nested = renderBlocks(block.blocks || []);
  nested.classList.add("nested-blocks");
  section.appendChild(nested);

  return section;
}

// Fallback for unknown types
function renderUnknown(block) {
  const el = document.createElement("div");
  el.classList.add("block-unknown");
  el.textContent = JSON.stringify(block, null, 2);
  return el;
}

async function sendMessage() {
  const message = document.getElementById("input").value;

  const res = await fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  const data = await res.json();
  console.log(data);

  // Parse JSON coming from ChatGPT
  let json;
  try {
    json =
      typeof data.response === "string"
        ? JSON.parse(data.response)
        : data.response;
  } catch (e) {
    console.error("Invalid JSON from AI:", e);
    json = {
      blocks: [{ type: "paragraph", text: "Error parsing response." }],
    };
  }

  // const json = {
  //   blocks: [
  //     {
  //       type: "heading",
  //       text: "Most Recent Diabetes-Related Clinical Studies (2 Cases)",
  //     },
  //     {
  //       type: "section",
  //       title: "Overview",
  //       blocks: [
  //         {
  //           type: "paragraph",
  //           text: "Two of the more recent diabetes-related clinical studies focus on simplified treatment approaches and digital tools for acute glycemic management. One has been completed, and one remains active but is not recruiting new participants.",
  //         },
  //       ],
  //     },
  //     {
  //       type: "section",
  //       title: "Digital Support for Acute Glycemic Emergencies",
  //       blocks: [
  //         {
  //           type: "card",
  //           title:
  //             "NCT02336217 – Glycemic Emergency Management (GEM); An App for Rapid Response to Hypoglycemic and Hyperglycemic Situations",
  //           blocks: [
  //             {
  //               type: "paragraph",
  //               text: "This study evaluates a mobile application designed to guide rapid responses to both hypoglycemic and hyperglycemic events. The focus is on real‑time decision support for patients or caregivers during acute glycemic crises, aiming to standardize steps such as symptom recognition, initial at‑home management, and thresholds for seeking urgent medical care.",
  //             },
  //             {
  //               type: "paragraph",
  //               text: "Although formal trial phase is not specified (study type listed as N/A), the project functions as an implementation/management study rather than a drug trial. It is currently active but not recruiting, indicating ongoing follow‑up or analysis of previously enrolled participants.",
  //             },
  //             {
  //               type: "bullet_list",
  //               items: [
  //                 "Study type: Non‑drug intervention (digital health tool)",
  //                 "Status: Active, not recruiting",
  //                 "Primary focus: Hypoglycemia and hyperglycemia emergency management via app‑based guidance",
  //                 "Potential impact: May improve safety, reduce delays in care, and support more consistent management of acute glycemic events.",
  //               ],
  //             },
  //           ],
  //         },
  //       ],
  //     },
  //     {
  //       type: "section",
  //       title: "Simplified Diabetes Treatment Approaches",
  //       blocks: [
  //         {
  //           type: "card",
  //           title: "NCT03258268 – Easy Diabetes Treatment Study 1",
  //           blocks: [
  //             {
  //               type: "paragraph",
  //               text: "This completed study, started in August 2017, centers on making diabetes treatment easier to implement, likely through simplified therapeutic regimens, delivery methods, or care pathways. The focus is on feasibility and practicality rather than on a specific new drug or device, which is reflected in the study type designation as N/A rather than a traditional drug trial phase.",
  //             },
  //             {
  //               type: "bullet_list",
  //               items: [
  //                 "Study type: Non‑traditional interventional or management study (no specified phase)",
  //                 "Status: Completed",
  //                 "Primary theme: Simplification of diabetes treatment to improve day‑to‑day management and adherence",
  //                 "Potential impact: Could inform strategies that reduce treatment complexity and improve real‑world usability of diabetes care plans.",
  //               ],
  //             },
  //           ],
  //         },
  //       ],
  //     },
  //   ],
  // };

  const output = document.getElementById("chat-output");

  output.innerHTML = ""; // clear
  const rendered = renderBlocks(json.blocks);
  rendered.classList.add("fade");
  output.appendChild(rendered);

  // Auto-scroll new content into view
  output.scrollTop = output.scrollHeight;
}

/**
"{
  "blocks": [
    {
      "type": "heading",
      "text": "Summary of 3 Recent Diabetes-Related Studies"
    },
    {
      "type": "section",
      "title": "Overview",
      "blocks": [
        {
          "type": "paragraph",
          "text": "Three recent studies focus on digital support for glycemic emergencies, simplified diabetes treatment, and nutritional supplementation in type 2 diabetes. All are non-drug, non-pharmacologic intervention studies (study type reported as N/A)."
        }
      ]
    },
    {
      "type": "section",
      "title": "Digital and Decision-Support Intervention",
      "blocks": [
        {
          "type": "card",
          "title": "NCT02336217 – Glycemic Emergency Management (GEM)",
          "items": [
            {
              "label": "Full title",
              "value": "Glycemic Emergency Management (GEM); An App for Rapid Response to Hypoglycemic and Hyperglycemic Situations"
            },
            {
              "label": "Design / type",
              "value": "Interventional; study type listed as N/A (non-drug/other intervention)."
            },
            {
              "label": "Clinical focus",
              "value": "Management of acute glycemic emergencies (hypoglycemia and hyperglycemia), likely in people with diabetes at risk for large glucose excursions."
            },
            {
              "label": "Intervention concept",
              "value": "Use of a mobile application (GEM app) to guide rapid recognition and response to low or high blood glucose events."
            },
            {
              "label": "Status",
              "value": "Active, not recruiting."
            },
            {
              "label": "Start date",
              "value": "September 2014"
            },
            {
              "label": "Key clinical relevance",
              "value": "Addresses patient-facing decision support during acute glycemic crises, with potential to reduce severe hypoglycemia, emergency visits, and delayed treatment of hyperglycemia."
            }
          ]
        }
      ]
    },
    {
      "type": "section",
      "title": "Simplified Diabetes Treatment Approaches",
      "blocks": [
        {
          "type": "card",
          "title": "NCT03258268 – Easy Diabetes Treatment Study 1",
          "items": [
            {
              "label": "Full title",
              "value": "Easy Diabetes Treatment Study 1"
            },
            {
              "label": "Design / type",
              "value": "Interventional; study type N/A, suggesting focus on care model, education, or device/behavioral intervention rather than a new drug."
            },
            {
              "label": "Clinical focus",
              "value": "Making diabetes treatment simpler or more accessible, likely through streamlined regimens, education, or tools to help with daily management."
            },
            {
              "label": "Status",
              "value": "Completed."
            },
            {
              "label": "Start date",
              "value": "August 7, 2017"
            },
            {
              "label": "Key clinical relevance",
              "value": "Targets practical barriers in routine diabetes care, potentially improving adherence, self-management, and glycemic control through simplification of treatment."
            }
          ]
        }
      ]
    },
    {
      "type": "section",
      "title": "Nutritional / Metabolic Supplementation in Type 2 Diabetes",
      "blocks": [
        {
          "type": "card",
          "title": "NCT05477368 – Prolonged Ketone Supplementation in Type 2 Diabetes",
          "items": [
            {
              "label": "Full title",
              "value": "Examining the Feasibility of Prolonged Ketone Supplement Drink Consumption in Adults With Type 2 Diabetes"
            },
            {
              "label": "Design / type",
              "value": "Interventional; study type N/A, focusing on a nutritional/metabolic supplement rather than a conventional drug."
            },
            {
              "label": "Clinical focus",
              "value": "Adults with type 2 diabetes; prolonged consumption of a ketone supplement drink."
            },
            {
              "label": "Main objective",
              "value": "Feasibility and tolerability of long-term exogenous ketone intake in people with type 2 diabetes, with implications for glycemic control, metabolic health, and patient acceptability."
            },
            {
              "label": "Status",
              "value": "Recruitment status listed as unknown."
            },
            {
              "label": "Start date",
              "value": "September 28, 2022"
            },
            {
              "label": "Key clinical relevance",
              "value": "Explores a non-pharmacologic metabolic strategy that could modulate glucose utilization and energy metabolism, potentially complementing standard type 2 diabetes management."
            }
          ]
        }
      ]
    },
    {
      "type": "section",
      "title": "Patterns Across the Three Studies",
      "blocks": [
        {
          "type": "bullet_list",
          "items": [
            "All three are interventional studies categorized as N/A for phase, indicating focus on devices, apps, education, or nutritional/metabolic strategies rather than new drugs.",
            "They target different aspects of diabetes care: acute emergency management (GEM app), simplification of routine treatment (Easy Diabetes Treatment Study 1), and metabolic supplementation (ketone drinks) in type 2 diabetes.",
            "Collectively, they emphasize real-world usability: rapid-response tools, easier treatment regimens, and feasible long-term supplements rather than solely pharmacologic innovation."
          ]
        }
      ]
    }
  ]
}"
 */

/*
"{
  "blocks": [
    {
      "type": "heading",
      "level": 1,
      "text": "Summary of 3 Recent Diabetes-Related Studies"
    },
    {
      "type": "section",
      "blocks": [
        {
          "type": "card",
          "title": "NCT02336217",
          "subtitle": "Glycemic Emergency Management (GEM); An App for Rapid Response to Hypoglycemic and Hyperglycemic Situations",
          "blocks": [
            {
              "type": "paragraph",
              "text": "Study type: N/A"
            },
            {
              "type": "paragraph",
              "text": "Phase: Not specified"
            },
            {
              "type": "paragraph",
              "text": "Status: ACTIVE_NOT_RECRUITING"
            },
            {
              "type": "paragraph",
              "text": "Primary focus: Development and evaluation of a mobile application (GEM) designed to support rapid response in glycemic emergencies, including both hypoglycemia and hyperglycemia."
            },
            {
              "type": "paragraph",
              "text": "Population/condition: Diabetes-related glycemic emergencies (specific condition details not provided)."
            },
            {
              "type": "paragraph",
              "text": "Intervention: Use of the GEM app (details not specified)."
            },
            {
              "type": "paragraph",
              "text": "Geographic location: Not specified."
            },
            {
              "type": "paragraph",
              "text": "Start date: 2014-09"
            },
            {
              "type": "paragraph",
              "text": "Completion dates: Not reported."
            }
          ]
        },
        {
          "type": "card",
          "title": "NCT03258268",
          "subtitle": "Easy Diabetes Treatment Study 1",
          "blocks": [
            {
              "type": "paragraph",
              "text": "Study type: N/A"
            },
            {
              "type": "paragraph",
              "text": "Phase: Not specified"
            },
            {
              "type": "paragraph",
              "text": "Status: COMPLETED"
            },
            {
              "type": "paragraph",
              "text": "Primary focus: Evaluation of an \"easy\" or simplified approach to diabetes treatment (specific therapeutic strategy not detailed)."
            },
            {
              "type": "paragraph",
              "text": "Population/condition: Diabetes (more specific condition details not provided)."
            },
            {
              "type": "paragraph",
              "text": "Interventions: Not specified."
            },
            {
              "type": "paragraph",
              "text": "Geographic location: Not specified."
            },
            {
              "type": "paragraph",
              "text": "Start date: 2017-08-07"
            },
            {
              "type": "paragraph",
              "text": "Completion dates: Not reported."
            }
          ]
        },
        {
          "type": "card",
          "title": "NCT05477368",
          "subtitle": "Examining the Feasibility of Prolonged Ketone Supplement Drink Consumption in Adults With Type 2 Diabetes",
          "blocks": [
            {
              "type": "paragraph",
              "text": "Study type: N/A"
            },
            {
              "type": "paragraph",
              "text": "Phase: Not specified"
            },
            {
              "type": "paragraph",
              "text": "Status: UNKNOWN"
            },
            {
              "type": "paragraph",
              "text": "Primary focus: Feasibility of prolonged consumption of ketone supplement drinks in adults with type 2 diabetes, likely examining safety, tolerability, and practicality of sustained use."
            },
            {
              "type": "paragraph",
              "text": "Population/condition: Adults with type 2 diabetes."
            },
            {
              "type": "paragraph",
              "text": "Intervention: Prolonged use of ketone supplement drinks (specific formulation and regimen not provided)."
            },
            {
              "type": "paragraph",
              "text": "Geographic location: Not specified."
            },
            {
              "type": "paragraph",
              "text": "Start date: 2022-09-28"
            },
            {
              "type": "paragraph",
              "text": "Completion dates: Not reported."
            }
          ]
        }
      ]
    },
    {
      "type": "section",
      "blocks": [
        {
          "type": "heading",
          "level": 2,
          "text": "Pattern Summary"
        },
        {
          "type": "bullet_list",
          "bullets": [
            "All three studies are diabetes-related but differ in focus: acute glycemic emergency management (GEM app), simplified diabetes treatment, and nutritional supplementation with ketone drinks in type 2 diabetes.",
            "Study statuses vary: one is active but not recruiting, one is completed, and one has unknown status.",
            "Key methodological details (phase, specific interventions, outcomes, and locations) are not provided in the available data for any of the three studies."
          ]
        }
      ]
    }
  ]
}"
*/

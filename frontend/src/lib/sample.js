// SAMPLE DATA for the landing page only. The text is invented. The signals and points are real output of the
// backend rule engine run on this text (ML stage omitted), so the illustration matches how the product behaves.
export const SAMPLE_PARTS = [
  { t: "" , m: null },
  { t: "Urgent hiring!", m: "urgency" },
  { t: " Data entry work from home. " },
  { t: "Earn Rs 45000 per month", m: "salary" },
  { t: ", " },
  { t: "no experience needed", m: "promise" },
  { t: ". " },
  { t: "Pay Rs 999 registration fee", m: "fee" },
  { t: " to confirm your seat. Contact " },
  { t: "hr.jobs2024@gmail.com", m: "email" },
];
export const SAMPLE_SIGNALS = [
  { key: "fee", title: "Registration/Training Fee", points: 30 },
  { key: "urgency", title: "Urgency Tactics", points: 20 },
  { key: "promise", title: "Unrealistic Promises", points: 20 },
  { key: "email", title: "Personal Email Contact", points: 25 },
  { key: "salary", title: "Salary above typical range", points: 15 },
];
export const SAMPLE_TOTAL = { raw: 110, capped: 100 };

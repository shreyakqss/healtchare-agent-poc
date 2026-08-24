/** Quick-start demo personas. Ages/conditions mirror backend/data/hms/patients.yaml
 * exactly, so picking one and linking pulls a real hospital record, not just a name.
 * The `tag` is a neutral symptom category, never an urgency word - the patient view
 * never shows priority, and a demo picker should not leak it either.
 */

export interface SamplePatient {
  /** Matches app/services/quick_start.py::QUICK_START_PATIENTS on the backend. */
  key: string;
  mrn: string;
  name: string;
  age: number;
  sex: string;
  tag: string;
  headline: string;
  openingLine: string;
}

export const SAMPLE_PATIENTS: SamplePatient[] = [
  {
    key: "arjun",
    mrn: "MRN-10021",
    name: "Arjun Mehta",
    age: 63,
    sex: "male",
    tag: "Sudden symptom",
    headline: "Chest pain since this morning",
    openingLine: "I've been having a tight chest pain since this morning. It comes and goes.",
  },
  {
    key: "priya",
    mrn: "MRN-10022",
    name: "Priya Nair",
    age: 51,
    sex: "female",
    tag: "Ongoing cough",
    headline: "Cough for three weeks, wheezing at night",
    openingLine: "I have had a persistent cough for about three weeks now, with some wheezing at night.",
  },
  {
    key: "meera",
    mrn: "MRN-10023",
    name: "Meera Iyer",
    age: 44,
    sex: "female",
    tag: "Fever, new medicine",
    headline: "Fever and sore throat, started a new medicine",
    openingLine: "I've had a fever and sore throat for two days. I started amoxicillin yesterday and I think I'm allergic to it.",
  },
  {
    key: "dev",
    mrn: "MRN-10024",
    name: "Dev Sharma",
    age: 34,
    sex: "male",
    tag: "Recurring headache",
    headline: "Headache for three weeks, behind the eyes",
    openingLine: "I've had a bad headache for about three weeks, mostly behind my eyes.",
  },
  {
    key: "kavita",
    mrn: "MRN-10025",
    name: "Kavita Rao",
    age: 29,
    sex: "female",
    tag: "Skin irritation",
    headline: "Itchy rash on both arms",
    openingLine: "I've got an itchy rash on my arms. It started about four days ago after I changed washing powder.",
  },
  {
    key: "rohan",
    mrn: "MRN-10026",
    name: "Rohan Banerjee",
    age: 57,
    sex: "male",
    tag: "Joint pain",
    headline: "Sore, swollen knee for a week",
    openingLine: "My knee has been sore and swollen for about a week, especially going up stairs.",
  },
];

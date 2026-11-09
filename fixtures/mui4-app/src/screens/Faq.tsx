import {
  ExpansionPanel,
  ExpansionPanelDetails,
  ExpansionPanelSummary,
  Link,
  Typography,
} from '@material-ui/core';
import ExpandMoreIcon from '@material-ui/icons/ExpandMore';

interface Question {
  id: string;
  question: string;
  answer: string;
}

const QUESTIONS: Question[] = [
  {
    id: 'export',
    question: 'How do I export my data?',
    answer: 'Open Users and choose Export CSV. The file includes every user that matches your filter.',
  },
  {
    id: 'delete',
    question: 'Can I delete my account?',
    answer: 'Yes. Go to Account and choose Delete account. This cannot be undone.',
  },
  {
    id: 'offices',
    question: 'Where are your offices?',
    answer: 'Use Search to find the office nearest to you.',
  },
];

export function Faq() {
  return (
    <section aria-labelledby="faq-title">
      <Typography id="faq-title" variant="h5" component="h1" gutterBottom>
        Frequently asked questions
      </Typography>
      {QUESTIONS.map((q) => (
        <ExpansionPanel key={q.id}>
          <ExpansionPanelSummary
            expandIcon={<ExpandMoreIcon />}
            id={`${q.id}-header`}
            aria-controls={`${q.id}-content`}
          >
            <Typography>{q.question}</Typography>
          </ExpansionPanelSummary>
          <ExpansionPanelDetails>
            <Typography>{q.answer}</Typography>
          </ExpansionPanelDetails>
        </ExpansionPanel>
      ))}
      <Typography variant="body2">
        Still stuck? <Link href="mailto:support@example.com">Contact support</Link>
      </Typography>
    </section>
  );
}

const COPY = {
  employees: {
    title: 'Employees',
    text: 'Employee registry, roles, shifts and availability. Full page arrives in the next phase.',
  },
  tasks: {
    title: 'Tasks',
    text: 'Task creation, assignment and progress tracking. Full page arrives in the next phase.',
  },
  machines: {
    title: 'Machines',
    text: 'Machine registry, health status and maintenance history. Full page arrives in the next phase.',
  },
  orders: {
    title: 'Orders',
    text: 'Customer orders, priorities and deadlines. Full page arrives in the next phase.',
  },
  production: {
    title: 'Production',
    text: 'Production runs linked to orders, tasks and machines. Full page arrives in the next phase.',
  },
  iot: {
    title: 'IoT Monitoring',
    text: 'Live telemetry from the factory floor. See the IoT Monitoring page; demo traffic comes from the built-in Simulator page.',
  },
  ai: {
    title: 'AI Assistant',
    text: 'AI-powered administrative assistant. Contracts are defined by the second developer — this page stays a placeholder until then.',
  },
};

export default function PlaceholderPage({ page }) {
  const copy = COPY[page] || { title: page, text: '' };
  return (
    <div className="page">
      <section className="panel placeholder">
        <h2>{copy.title}</h2>
        <p className="muted">{copy.text}</p>
        <p className="muted">Backend APIs for this area already exist — only the UI is pending.</p>
      </section>
    </div>
  );
}

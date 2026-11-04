export default function PortalRegister() {
  return (
    <main className="container">
      <section className="card">
        <p className="eyebrow">ACCOUNT ACTIVATION</p>
        <h1>Get portal access</h1>
        <p className="muted">Student and parent accounts are provisioned through your school to ensure each account is linked to the correct learner record.</p>
        <p>Please contact your school administrator with your student number and activation slip. Once your Supabase Auth account has been created and linked, you can sign in securely.</p>
        <a href="/portal/login">Return to sign in →</a>
      </section>
    </main>
  );
}

import Link from 'next/link';

export default function PaynowReturn() {
  return (
    <div className="container">
      <div className="card">
        <h1>Payment response received</h1>
        <p>
          Paynow has returned you to Chikoro Digital. Your payment is not
          considered complete until the server verifies the payment notification.
        </p>
        <p>Return to your fee statement and refresh it to check the latest balance.</p>
        <Link href="/portal/fees">Return to fee status</Link>
      </div>
    </div>
  );
}

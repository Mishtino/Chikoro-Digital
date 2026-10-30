import { useState } from 'react';
import { useRouter } from 'next/router';

export default function Home() {
  const [code, setCode] = useState('');
  const router = useRouter();
  return (
    <div className="container">
      <div className="card">
        <h1>Chikoro Digital</h1>
        <p>Enter your school code to access the student and parent portal.</p>
        <input placeholder="School code" value={code} onChange={(e) => setCode(e.target.value)} />
        <button onClick={() => code && router.push(`/portal/login?school=${encodeURIComponent(code)}`)}>Continue</button>
      </div>
    </div>
  );
}

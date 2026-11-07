import Head from 'next/head';
import '../styles/globals.css';

export default function App({ Component, pageProps }) {
  return <>
    <Head>
      <title>Chikoro Digital</title>
      <meta name="application-name" content="Chikoro Digital" />
      <meta name="theme-color" content="#0F2A43" />
      <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
      <link rel="apple-touch-icon" href="/app-icon.svg" />
    </Head>
    <Component {...pageProps} />
  </>;
}

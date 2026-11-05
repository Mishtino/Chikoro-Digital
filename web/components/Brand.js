import Image from 'next/image';

export default function Brand({ compact = false, inverse = false, className = '' }) {
  const src = compact
    ? (inverse ? '/logo-compact-dark.svg' : '/logo-compact-light.svg')
    : (inverse ? '/logo-primary-dark.svg' : '/logo-primary-light.svg');
  return <Image src={src} alt={compact ? 'Chikoro' : 'Chikoro Digital'} width={compact ? 165 : 310} height={50} priority className={className} style={{ width: compact ? 165 : 'min(100%, 310px)', height: 'auto' }} />;
}

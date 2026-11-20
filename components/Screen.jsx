'use client';
import { useEffect } from 'react';
export default function Screen({ markup, script, bodyClass }) {
  useEffect(() => {
    document.body.className = bodyClass;
    new Function(script)();
    return () => { document.body.className = ''; };
  }, [script, bodyClass]);
  return <div dangerouslySetInnerHTML={{ __html: markup }} />;
}

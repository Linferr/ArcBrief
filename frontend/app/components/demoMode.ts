export const isReadOnlyDemo = (): boolean =>
  process.env.NEXT_PUBLIC_ARCBRIEF_READ_ONLY === '1';

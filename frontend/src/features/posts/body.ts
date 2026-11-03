export const MAX_BODY = 120;

export const length = (value: string) => [...value].length;

export const bodyLength = (value: string) => length(value.trim());

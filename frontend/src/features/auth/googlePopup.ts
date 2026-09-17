export const GOOGLE_POPUP_CHANNEL = 'ck-google-auth';
export const GOOGLE_POPUP_FLOW_KEY = 'ck-google-popup-flow';

export type GooglePopupMessage = { type: 'complete'; flowId: string };

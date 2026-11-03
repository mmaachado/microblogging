import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { getCookie, setCookie } from "@/lib/cookies";
import en from "./locales/en.json";
import ptBR from "./locales/pt-BR.json";

export const LANGUAGES = ["pt-BR", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

function readLanguage(): Language {
  const value = getCookie("lang");
  return value === "en" || value === "pt-BR" ? value : "pt-BR";
}

function applyLanguage(language: Language): void {
  document.documentElement.lang = language;
}

void i18n.use(initReactI18next).init({
  resources: { "pt-BR": { translation: ptBR }, en: { translation: en } },
  lng: readLanguage(),
  fallbackLng: "pt-BR",
  interpolation: { escapeValue: false },
});

applyLanguage(readLanguage());

export function setLanguage(language: Language): void {
  setCookie("lang", language);
  applyLanguage(language);
  void i18n.changeLanguage(language);
}

export default i18n;

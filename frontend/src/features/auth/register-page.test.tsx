import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { RegisterPage } from "./register-page";

describe("RegisterPage", () => {
  it("shows the e-mail notice", () => {
    renderWithProviders(<RegisterPage />);
    expect(
      screen.getByText(/Seu e-mail fica guardado como você digitou/),
    ).toBeInTheDocument();
  });

  it("keeps submit disabled until notice is checked and passwords match", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);
    const submit = screen.getByRole("button", { name: "Criar conta" });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText("E-mail"), "a@example.com");
    await user.type(screen.getByLabelText("Senha"), "correct horse battery");
    await user.type(
      screen.getByLabelText("Confirmar senha"),
      "something else entirely",
    );
    await user.click(screen.getByRole("checkbox", { name: "Li e entendi" }));
    expect(submit).toBeDisabled();

    await user.clear(screen.getByLabelText("Confirmar senha"));
    await user.type(
      screen.getByLabelText("Confirmar senha"),
      "correct horse battery",
    );
    expect(submit).toBeEnabled();

    await user.click(screen.getByRole("checkbox", { name: "Li e entendi" }));
    expect(submit).toBeDisabled();
  });
});

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthGate } from "./auth";
import CustomerQrApp from "./CustomerQrApp";
import { customerQrTokenFromPath } from "./routing";
import "./styles.css";

const customerQrToken = customerQrTokenFromPath(window.location.pathname);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {customerQrToken ? <CustomerQrApp token={customerQrToken} /> : <AuthGate><App /></AuthGate>}
  </StrictMode>,
);

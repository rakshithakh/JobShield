import { Component } from "react";
import { Alert } from "./ui";

export default class ErrorBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error) { console.error("UI error:", error.name); }
  render() {
    if (this.state.failed) {
      return (
        <div className="mx-auto max-w-2xl p-6">
          <Alert title="This page hit an unexpected problem" action={<a className="font-semibold underline" href="/">Go to the home page</a>}>
            Reloading usually fixes it. Your saved analyses are not affected.
          </Alert>
        </div>
      );
    }
    return this.props.children;
  }
}

import LoginForm from "./login-form";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-6 py-16 font-sans dark:bg-black">
      <main className="flex w-full max-w-3xl flex-col items-center gap-8">
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
            EndNote
          </h1>
          <p className="max-w-md text-base text-zinc-600 dark:text-zinc-400">
            Ask questions about your own documents. Sign in to upload, and
            they will be indexed page by page.
          </p>
        </div>
        <LoginForm />
      </main>
    </div>
  );
}

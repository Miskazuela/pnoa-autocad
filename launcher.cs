using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

public class LauncherForm : Form
{
    private Process serverProcess;
    private Label statusLabel;
    private Button btnOpenBrowser;
    private Button btnExit;
    private string port = "8501";
    private string appUrl;

    public LauncherForm()
    {
        appUrl = "http://localhost:" + port;

        this.Text = "PNOA to AutoCAD - Servidor Local";
        this.Size = new Size(480, 260);
        this.StartPosition = FormStartPosition.CenterScreen;
        this.FormBorderStyle = FormBorderStyle.FixedDialog;
        this.MaximizeBox = false;
        this.BackColor = Color.FromArgb(249, 250, 251);

        Label titleLabel = new Label();
        titleLabel.Text = "PNOA to AutoCAD";
        titleLabel.Font = new Font("Segoe UI", 15, FontStyle.Bold);
        titleLabel.ForeColor = Color.FromArgb(30, 64, 175);
        titleLabel.Location = new Point(25, 20);
        titleLabel.Size = new Size(420, 32);
        this.Controls.Add(titleLabel);

        Label subLabel = new Label();
        subLabel.Text = "Extractor Georreferenciado Oficial (IGN Espana)";
        subLabel.Font = new Font("Segoe UI", 9, FontStyle.Regular);
        subLabel.ForeColor = Color.FromArgb(107, 114, 128);
        subLabel.Location = new Point(26, 54);
        subLabel.Size = new Size(420, 20);
        this.Controls.Add(subLabel);

        statusLabel = new Label();
        statusLabel.Text = "Iniciando servidor de cartografia...";
        statusLabel.Font = new Font("Segoe UI", 10, FontStyle.Regular);
        statusLabel.ForeColor = Color.FromArgb(31, 41, 55);
        statusLabel.Location = new Point(26, 88);
        statusLabel.Size = new Size(420, 42);
        this.Controls.Add(statusLabel);

        btnOpenBrowser = new Button();
        btnOpenBrowser.Text = "Abrir en Navegador";
        btnOpenBrowser.Font = new Font("Segoe UI", 9, FontStyle.Bold);
        btnOpenBrowser.Size = new Size(195, 40);
        btnOpenBrowser.Location = new Point(25, 148);
        btnOpenBrowser.BackColor = Color.FromArgb(37, 99, 235);
        btnOpenBrowser.ForeColor = Color.White;
        btnOpenBrowser.FlatStyle = FlatStyle.Flat;
        btnOpenBrowser.Cursor = Cursors.Hand;
        btnOpenBrowser.Click += new EventHandler((s, e) => {
            try { Process.Start(appUrl); } catch {}
        });
        this.Controls.Add(btnOpenBrowser);

        btnExit = new Button();
        btnExit.Text = "Detener y Salir";
        btnExit.Font = new Font("Segoe UI", 9, FontStyle.Regular);
        btnExit.Size = new Size(195, 40);
        btnExit.Location = new Point(245, 148);
        btnExit.BackColor = Color.FromArgb(243, 244, 246);
        btnExit.ForeColor = Color.FromArgb(31, 41, 55);
        btnExit.FlatStyle = FlatStyle.Flat;
        btnExit.Cursor = Cursors.Hand;
        btnExit.Click += new EventHandler((s, e) => { this.Close(); });
        this.Controls.Add(btnExit);

        this.FormClosing += new FormClosingEventHandler(LauncherForm_FormClosing);
        this.Shown += new EventHandler(LauncherForm_Shown);
    }

    private void LauncherForm_Shown(object sender, EventArgs e)
    {
        StartStreamlit();
    }

    private void StartStreamlit()
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string pythonExe = null;

        string runtimePy = Path.Combine(baseDir, "runtime", "python.exe");
        string dotRuntimePy = Path.Combine(baseDir, ".runtime", "python.exe");

        if (File.Exists(runtimePy)) {
            pythonExe = runtimePy;
        } else if (File.Exists(dotRuntimePy)) {
            pythonExe = dotRuntimePy;
        } else {
            pythonExe = "python.exe";
        }

        string appScript = Path.Combine(baseDir, "app.py");
        if (!File.Exists(appScript))
        {
            MessageBox.Show("No se encontro el archivo 'app.py' en:\n" + baseDir, "PNOA to AutoCAD", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Application.Exit();
            return;
        }

        try
        {
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExe;
            psi.Arguments = string.Format("-m streamlit run \"{0}\" --server.port={1} --browser.serverAddress=\"localhost\" --server.headless=false", appScript, port);
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;

            serverProcess = Process.Start(psi);
            statusLabel.Text = "Servidor activo en: " + appUrl + "\nPuedes minimizar esta ventana mientras usas la app.";
        }
        catch (Exception ex)
        {
            MessageBox.Show("No se pudo iniciar el servidor local:\n" + ex.Message + "\n\nSi no tienes Python instalado, ejecuta primero 'iniciar_app.bat' para configurar el entorno portable.", "PNOA to AutoCAD", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            Application.Exit();
        }
    }

    private void LauncherForm_FormClosing(object sender, FormClosingEventArgs e)
    {
        if (serverProcess != null && !serverProcess.HasExited)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo("taskkill", string.Format("/F /T /PID {0}", serverProcess.Id));
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                Process p = Process.Start(psi);
                if (p != null) p.WaitForExit(2000);
            }
            catch {}
        }
    }

    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new LauncherForm());
    }
}

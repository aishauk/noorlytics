using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;

namespace LegacyBillingSystem
{
    public class Program
    {
        public static List<Customer> customers = new List<Customer>();
        public static string exportFolder = "C:\\Exports\\";
        public static bool isRunning = true;
        public static int processedFiles = 0;
        public static string lastError = "";

        static void Main(string[] args)
        {
            Console.WriteLine("Legacy Billing System v2.1");
            Console.WriteLine("Starting system...");

            LoadCustomers();

            while (isRunning)
            {
                Console.WriteLine("");
                Console.WriteLine("1. Process invoices");
                Console.WriteLine("2. Export report");
                Console.WriteLine("3. Print statistics");
                Console.WriteLine("4. Sync customers");
                Console.WriteLine("5. Exit");

                var input = Console.ReadLine();

                if (input == "1")
                {
                    ProcessInvoices();
                }
                else if (input == "2")
                {
                    ExportReport();
                }
                else if (input == "3")
                {
                    PrintStatistics();
                }
                else if (input == "4")
                {
                    SyncCustomers();
                }
                else if (input == "5")
                {
                    isRunning = false;
                }
                else
                {
                    Console.WriteLine("Unknown option");
                }
            }
        }

        public static void LoadCustomers()
        {
            Console.WriteLine("Loading customers...");

            if (File.Exists("customers.txt"))
            {
                string[] rows = File.ReadAllLines("customers.txt");

                for (int i = 0; i < rows.Length; i++)
                {
                    string[] data = rows[i].Split(';');

                    Customer customer = new Customer();

                    customer.Id = Convert.ToInt32(data[0]);
                    customer.Name = data[1];
                    customer.Email = data[2];
                    customer.Country = data[3];
                    customer.IsActive = data[4] == "1";

                    customers.Add(customer);
                }
            }

            Console.WriteLine("Loaded " + customers.Count + " customers");
        }

        public static void ProcessInvoices()
        {
            Console.WriteLine("Processing invoices...");

            string[] files = Directory.GetFiles("C:\\Invoices\\");

            for (int i = 0; i < files.Length; i++)
            {
                string file = files[i];

                try
                {
                    string content = File.ReadAllText(file);

                    if (content.Contains("ERROR"))
                    {
                        Console.WriteLine("Invoice contains invalid data");
                    }
                    else
                    {
                        Thread.Sleep(500);

                        string output = "";
                        output += "PROCESSED:" + Environment.NewLine;
                        output += "FILE:" + file + Environment.NewLine;
                        output += "DATE:" + DateTime.Now + Environment.NewLine;
                        output += "STATUS:SUCCESS" + Environment.NewLine;

                        File.WriteAllText(exportFolder + "result_" + processedFiles + ".txt", output);

                        processedFiles++;
                    }
                }
                catch (Exception ex)
                {
                    lastError = ex.Message;

                    File.AppendAllText(
                        "system.log",
                        DateTime.Now + " ERROR: " + ex.Message + Environment.NewLine
                    );
                }
            }
        }

        public static void ExportReport()
        {
            Console.WriteLine("Generating report...");

            StringBuilder builder = new StringBuilder();

            builder.AppendLine("CUSTOMER REPORT");
            builder.AppendLine("---------------------------");

            for (int i = 0; i < customers.Count; i++)
            {
                Customer customer = customers[i];

                builder.AppendLine(
                    customer.Id + "," +
                    customer.Name + "," +
                    customer.Email + "," +
                    customer.Country + "," +
                    customer.IsActive
                );
            }

            builder.AppendLine("---------------------------");
            builder.AppendLine("Generated: " + DateTime.Now);

            File.WriteAllText(exportFolder + "customer_report.txt", builder.ToString());

            Console.WriteLine("Report exported");
        }

        public static void PrintStatistics()
        {
            Console.WriteLine("");
            Console.WriteLine("System statistics");
            Console.WriteLine("----------------------");
            Console.WriteLine("Customers: " + customers.Count);
            Console.WriteLine("Processed files: " + processedFiles);
            Console.WriteLine("Last error: " + lastError);

            int activeCustomers = 0;

            for (int i = 0; i < customers.Count; i++)
            {
                if (customers[i].IsActive)
                {
                    activeCustomers++;
                }
            }

            Console.WriteLine("Active customers: " + activeCustomers);
        }

        public static void SyncCustomers()
        {
            Console.WriteLine("Syncing customers with remote server...");

            try
            {
                WebClient client = new WebClient();

                string response = client.DownloadString(
                    "http://legacy-api.internal/customers"
                );

                File.WriteAllText("backup_customers.json", response);

                Console.WriteLine("Sync completed");
            }
            catch (Exception ex)
            {
                Console.WriteLine("Sync failed");
                Console.WriteLine(ex.Message);
            }
        }
    }

    public class Customer
    {
        public int Id;
        public string Name;
        public string Email;
        public string Country;
        public bool IsActive;
    }
}